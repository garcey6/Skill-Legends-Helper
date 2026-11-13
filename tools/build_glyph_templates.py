"""Build the 16x16 closed-set glyph library for hero nameplates.

The game font is not shipped, so render the unique characters from the 60 hero
names with the Windows CJK fonts.  The matcher keeps several font variants per
character and uses top-5 sequence constraints, which tolerates a different face.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "recognize"
SIZE = 16
FONTS = [
    ("simhei", r"C:\Windows\Fonts\simhei.ttf"),
    ("simsun", r"C:\Windows\Fonts\simsun.ttc"),
    ("msyh", r"C:\Windows\Fonts\msyh.ttc"),
    ("msyhbd", r"C:\Windows\Fonts\msyhbd.ttc"),
    ("dengb", r"C:\Windows\Fonts\Dengb.ttf"),
    ("stxihei", r"C:\Windows\Fonts\STXIHEI.TTF"),
]


def normalize(image: Image.Image) -> np.ndarray:
    image = image.convert("L")
    arr = np.asarray(image, dtype=np.float32)
    arr = arr - float(arr.mean())
    std = float(arr.std())
    if std < 1e-6:
        return np.zeros(SIZE * SIZE, dtype=np.float32)
    arr = arr / std
    return arr.reshape(-1)


def render_char(char: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    canvas = Image.new("L", (80, 80), 0)
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 40), char, font=font, fill=255, anchor="mm")
    bbox = canvas.getbbox()
    if not bbox:
        return np.zeros(SIZE * SIZE, dtype=np.float32)
    crop = canvas.crop(bbox).resize((SIZE, SIZE), Image.LANCZOS)
    return normalize(crop)


def main() -> int:
    heroes = json.loads((DATA / "heroes.json").read_text(encoding="utf-8"))["heroes"]
    names = [h["name"] for h in heroes]
    chars = sorted({ch for name in names for ch in name})
    fonts = []
    for name, path in FONTS:
        if Path(path).exists():
            try:
                fonts.append((name, ImageFont.truetype(path, 64)))
            except OSError:
                pass
    if not fonts:
        raise SystemExit("no CJK fonts found")

    vectors = []
    owners = []
    for char in chars:
        for font_name, font in fonts:
            vector = render_char(char, font)
            if np.abs(vector).sum() > 0:
                vectors.append([round(float(v), 5) for v in vector.tolist()])
                owners.append({"char": char, "font": font_name})
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "size": SIZE,
        "chars": chars,
        "fonts": [name for name, _ in fonts],
        "vectors": vectors,
        "owners": owners,
        "coverage": 1.0,
        "note": "Windows CJK font renderings; add real nameplate glyph samples to improve.",
    }
    (OUT / "glyphs.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print("chars", len(chars), "fonts", [name for name, _ in fonts], "vectors", len(vectors))
    print("wrote", OUT / "glyphs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
