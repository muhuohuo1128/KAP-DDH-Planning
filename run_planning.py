"""Supported CPU/GUI entry point; original planning calculations are unchanged."""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parent


def load_configuration(path):
    spec = importlib.util.spec_from_file_location("config", Path(path).resolve())
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    if not isinstance(config.PARAMS.get("PERSONALIZED_CONSTRAINTS_ENABLE"), bool):
        raise ValueError("PERSONALIZED_CONSTRAINTS_ENABLE must be Python True or False.")
    sys.modules["config"] = config
    return config


def load_core(config):
    original_print_exc = traceback.print_exc
    try:
        import planning_core as core
    finally:
        traceback.print_exc = original_print_exc
    for key in ("FOLDER_A", "FOLDER_B", "FOLDER_C", "FOLDER_C4", "FOLDER_C3", "FILE_D"):
        setattr(core, key, config.PATHS.get(key, ""))
    return core


def validate_case(config, case):
    """Reject missing/mismatched inputs instead of accepting a default scale."""
    import numpy as np
    import pandas as pd
    from PIL import Image
    if not case or case in (".", "..") or any(c in case for c in "/\\"):
        raise ValueError("--case must be a filename stem without folders or .png.")
    paths, params = config.PATHS, config.PARAMS
    image_path = Path(paths["FOLDER_A"]) / f"{case}.png"
    with Image.open(image_path) as im:
        size = im.size
    masks = [("FOLDER_B", "kjwy"), ("FOLDER_C4", "bks")]
    if paths.get("FOLDER_C3"):
        optional = Path(paths["FOLDER_C3"]) / f"{case}_bkx.png"
        if optional.is_file():
            masks.append(("FOLDER_C3", "bkx"))
        else:
            print("Notice: curve3 mask is absent; original core treats it as optional.")
    for key, suffix in masks:
        with Image.open(Path(paths[key]) / f"{case}_{suffix}.png") as im:
            if im.size != size:
                raise ValueError(f"{suffix} mask dimensions differ from the source image.")
            a = np.asarray(im.convert("L"))
            if not np.any((a == 1) | (a > 127)):
                raise ValueError(f"{suffix} mask has no foreground pixels.")
    txt = Path(paths["FOLDER_C"]) / f"{case}.txt"
    points = []
    landmark_text = txt.read_text(encoding="utf-8")
    if landmark_text.startswith("\ufeff"):
        raise ValueError("Save landmark TXT as UTF-8 without BOM; the original reader does not support BOM.")
    for line in landmark_text.splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 2:
            raise ValueError("Landmark rows must contain exactly x,y.")
        point = tuple(float(v) for v in parts)
        if not all(math.isfinite(v) for v in point):
            raise ValueError("Landmarks must contain finite coordinates.")
        points.append(point)
    if len(points) < 8:
        raise ValueError("At least eight ordered landmarks are required.")
    for i in (0, 2, 4, 6):
        if points[i] == points[i + 1]:
            raise ValueError("The two endpoints of each reference line must differ.")
    if params["PERSONALIZED_CONSTRAINTS_ENABLE"] and len(points) != params.get("KB_EXPECT_N_POINTS", 9):
        raise ValueError("Landmark count does not match KB_EXPECT_N_POINTS.")
    frame = pd.read_excel(paths["FILE_D"])
    stem_col = int(params["FILE_D_STEM_COL"]) - 1
    scale_col = int(params["FILE_D_SCALE_COL"]) - 1
    if min(stem_col, scale_col) < 0 or max(stem_col, scale_col) >= frame.shape[1]:
        raise ValueError("Configured scale-table columns are outside the workbook.")
    matches = frame[frame.iloc[:, stem_col].astype(str).str.strip() == case]
    if len(matches) != 1:
        raise ValueError("Scale table must contain exactly one row for this case.")
    scale = float(matches.iloc[0, scale_col])
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Scale must be a positive finite number in mm per pixel.")
    return {"mm_per_pixel": scale, "image_size": size, "landmark_count": len(points)}


def preflight_kb(config, core):
    if config.PARAMS["PERSONALIZED_CONSTRAINTS_ENABLE"]:
        idx, module = core._get_kb_index()
        if idx is None or module is None:
            raise RuntimeError(
                "Study-specific constraint mode was requested, but the required integration resources "
                "are not available in the current environment. Use the documented fixed-constraint "
                "demo or configure the required integration resources."
            )


def json_safe(value, replaced, path="$"):
    import numpy as np
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, dict):
        return {str(k): json_safe(v, replaced, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v, replaced, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, float) and not math.isfinite(value):
        replaced.append(path)
        return None
    return value


def run_case(config, core, case, level, output):
    info = validate_case(config, case)
    preflight_kb(config, core)
    kb_state = {"requested": config.PARAMS["PERSONALIZED_CONSTRAINTS_ENABLE"], "application_succeeded": None}
    original_apply = core._apply_personalized_constraint_ideals

    def observed_apply(*args, **kwargs):
        success = original_apply(*args, **kwargs)
        kb_state["application_succeeded"] = bool(success)
        return success

    core._apply_personalized_constraint_ideals = observed_apply
    core.update_constraint_ideals(level)
    try:
        results, curve_points, width = core.process_file_set_adaptive(
            case, show_individual_windows=False, use_gpu=False)
    finally:
        core._apply_personalized_constraint_ideals = original_apply
    payload = {
        "case_id": case, "crowe_level": level,
        "input_status": getattr(config, "INPUT_STATUS", "user-supplied; not independently validated"),
        "mode": "KB requested" if kb_state["requested"] else "fixed constraints",
        "kb_constraint_application": kb_state,
        "scale_and_dimensions": info, "image_width": width,
        "curve_points": curve_points, "plans": results,
    }
    replaced = []
    payload = json_safe(payload, replaced)
    payload["nonfinite_values_serialized_as_null"] = replaced
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Mode: {payload['mode']}; returned {len(results)} plan(s); saved {output}")
    if kb_state["requested"] and not kb_state["application_succeeded"]:
        print("NOTICE: original core fell back to fixed constraints for this case.")
    if not results:
        print("NOTICE: no plan returned. This is not evidence of anatomical feasibility.")
    return payload


def launch_gui(config, core):
    from PyQt5.QtWidgets import QApplication, QMessageBox
    original_print_exc = traceback.print_exc
    try:
        from planning_ui import PlanVisualizationUI
    finally:
        traceback.print_exc = original_print_exc
    preflight_kb(config, core)
    # Validate existing cases before starting; the original UI can also select new folders.
    image_dir = Path(config.PATHS["FOLDER_A"])
    for image_path in sorted(image_dir.glob("*.png")):
        validate_case(config, image_path.stem)
    Path(config.PATHS["SAVE_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = PlanVisualizationUI()
    window.gpu_acceleration_checkbox.setChecked(False)
    mode = "KB requested; legacy per-case fallback possible" if config.PARAMS["PERSONALIZED_CONSTRAINTS_ENABLE"] else "Fixed constraints"
    window.setWindowTitle(f"KAP-DDH Planning | {mode}")
    if not image_dir.exists() or not list(image_dir.glob("*.png")):
        QMessageBox.information(window, "Configure inputs", "No source images found. Read docs/INPUTS.md or use the synthetic demo configuration.")
    window.show()
    return app.exec_()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.py")
    parser.add_argument("--case", help="Filename stem without .png")
    parser.add_argument("--level", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--output", type=Path, help="Batch JSON; defaults to outputs/cli/<case>.json (not the GUI save schema)")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if not args.gui and not args.case:
        parser.error("Provide --case or --gui.")
    if not args.gui:
        os.environ.setdefault("MPLBACKEND", "Agg")
    config = load_configuration(args.config)
    core = load_core(config)
    if args.gui:
        return launch_gui(config, core)
    output = args.output or ROOT / "outputs" / "cli" / f"{args.case}.json"
    run_case(config, core, args.case, args.level, output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Planning failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
