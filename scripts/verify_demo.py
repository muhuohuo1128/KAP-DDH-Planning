"""Run the artificial example and compare all plan fields with its reference."""
from pathlib import Path
import json
import math
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def compare(actual, expected, path="plans"):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), f"Keys differ at {path}"
        for key in expected:
            compare(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"Length differs at {path}"
        for i, (a, e) in enumerate(zip(actual, expected)):
            compare(a, e, f"{path}[{i}]")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-6), f"Value differs at {path}: {actual} != {expected}"
    else:
        assert actual == expected, f"Value differs at {path}"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "result.json"
        subprocess.run([sys.executable, str(ROOT / "run_planning.py"), "--config",
                        str(ROOT / "examples/demo_config.py"), "--case", "SYNTHETIC_001",
                        "--level", "1", "--output", str(output)], check=True, timeout=60)
        actual = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "examples/expected/result.json").read_text(encoding="utf-8"))
    assert actual["mode"] == "fixed constraints"
    assert actual["image_width"] == 512
    assert not actual["kb_constraint_application"]["requested"]
    compare(actual["plans"], expected["plans"])
    print("PASS: synthetic CPU planning output matches the reference. This is not study-result validation.")


if __name__ == "__main__":
    main()
