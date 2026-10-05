"""Regenerate the artificial fixture; no patient data or anatomical validation."""
from pathlib import Path
from PIL import Image, ImageDraw
from openpyxl import Workbook

def prepare_fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    folders = {name: root / name for name in ("images", "rim", "landmarks", "upper", "lower")}
    for folder in folders.values():
        folder.mkdir(exist_ok=True)
    canvas = Image.new("RGB", (512, 512), (246, 248, 250))
    draw = ImageDraw.Draw(canvas)
    for x in range(0, 512, 32):
        draw.line((x, 0, x, 511), fill=(226, 230, 234))
    for y in range(0, 512, 32):
        draw.line((0, y, 511, y), fill=(226, 230, 234))
    draw.text((12, 12), "SYNTHETIC GEOMETRY - NOT A PATIENT IMAGE", fill=(0, 0, 0))
    points = [(156, 220), (356, 220), (80, 250), (80, 450),
              (220, 250), (220, 450), (400, 100), (400, 300), (120, 180)]
    for i in range(0, 8, 2):
        draw.line((*points[i], *points[i+1]), fill=(150, 160, 180), width=1)
    canvas.save(folders["images"] / "SYNTHETIC_001.png")
    rim = Image.new("L", (512, 512), 0)
    # One artificial candidate rim pixel keeps the full CPU search small.
    rim.putpixel((390, 130), 255)
    rim.save(folders["rim"] / "SYNTHETIC_001_kjwy.png")
    for name, suffix, y in (("upper", "bks", 450), ("lower", "bkx", 480)):
        mask = Image.new("L", (512, 512), 0)
        ImageDraw.Draw(mask).line((280, y, 500, y), fill=255, width=1)
        mask.save(folders[name] / ("SYNTHETIC_001_" + suffix + ".png"))
    (folders["landmarks"] / "SYNTHETIC_001.txt").write_text(
        "".join(f"{x},{y}\n" for x, y in points), encoding="utf-8")
    book = Workbook()
    sheet = book.active
    sheet.title = "Scale"
    sheet.append(["case_id", "mm_per_pixel"])
    sheet.append(["SYNTHETIC_001", 0.5])
    book.save(root / "scale.xlsx")
    return folders

if __name__ == "__main__":
    prepare_fixture(Path(__file__).resolve().parents[1] / "examples" / "synthetic")
    print("Generated examples/synthetic (artificial geometry only).")
