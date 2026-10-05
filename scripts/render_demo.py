"""Render the computed artificial example using the preserved core visualizer."""
from pathlib import Path
import json
import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
import run_planning


def main():
    config = run_planning.load_configuration(ROOT / "examples/demo_config.py")
    core = run_planning.load_core(config)
    output = ROOT / "outputs/cli/SYNTHETIC_001.json"
    payload = run_planning.run_case(config, core, "SYNTHETIC_001", 1, output)
    regular = [p for p in payload["plans"] if not p.get("is_special_fallback")]
    if not regular:
        raise RuntimeError("No regular plan was returned; no illustration rendered.")
    plan = regular[0]
    points = core.read_points_from_txt(str(ROOT / "examples/synthetic/landmarks/SYNTHETIC_001.txt"))
    rendered = core.visualize_results(
        str(ROOT / "examples/synthetic/images/SYNTHETIC_001.png"),
        points[:2], plan["outer_point"], plan["center_point"],
        plan["line6_angle_rad"], plan["line7_angle_rad"], plan["line1_eq"], plan["line4_eq"],
        circle_diameter=plan["safe_even_diameter"] / plan["scale_factor"],
        scale=plan["scale_factor"], ui_mode=True,
        is_special_fallback=plan["is_special_fallback"])
    target = ROOT / "outputs/cli/synthetic_best_plan.png"
    Image.fromarray(rendered[:, :, ::-1]).save(target)
    print(f"Synthetic illustration saved to {target}")


if __name__ == "__main__":
    main()
