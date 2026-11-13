"""Seed real nameplate glyphs from the two shipped draft frames.

Font renderings get most characters close, but some game glyphs (e.g. 法/师)
differ enough that font-only matching fails.  These known frames provide
actual glyph variants for the six names they contain.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.blobs import group_nameplates, segment_glyphs  # noqa: E402
from app.vision.glyphs import glyph_feature  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "recognize" / "glyphs.json"
LAYOUT = json.loads((DATA / "recognize" / "layout.json").read_text(encoding="utf-8"))
ROI = LAYOUT["rois"]["nameplates"]

# Fixture path -> (names, partitions of the detected glyph boxes into characters)
SEEDS = [
    (
        "samples/draft_001.png",
        ["森林游侠", "神秘法师", "魔镜"],
        [
            [[0], [1], [2], [3]],
            [[0], [1], [2, 3], [4]],
            [[0], [1, 2]],
        ],
    ),
    (
        "samples/window_draft.png",
        ["守财奴", "狂暴战将", "精灵牧师"],
        [
            [[0], [1], [2]],
            [[0, 1], [2], [3], [4]],
            [[0, 1], [2], [3], [4]],
        ],
    ),
]


def main() -> int:
    glyphs = json.loads(OUT.read_text(encoding="utf-8"))
    size = int(glyphs["size"])
    vectors = list(glyphs["vectors"])
    owners = list(glyphs["owners"])
    added = []
    for rel, names, partitions in SEEDS:
        path = ROOT / rel
        if not path.exists():
            print("missing seed frame", path)
            continue
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
        h, w = arr.shape[:2]
        boxes = segment_glyphs(arr, ROI, 72, 80, 0.025)
        groups = group_nameplates(boxes, w * 0.035, h)
        if len(groups) < 3:
            print("not enough nameplates in", rel, len(groups))
            continue
        for slot, (name, parts) in enumerate(zip(names, partitions)):
            group = groups[slot]
            if len(parts) != len(name):
                print("partition/name mismatch", rel, name)
                continue
            for char, indexes in zip(name, parts):
                selected = [group[i] for i in indexes if i < len(group)]
                if not selected:
                    continue
                x0 = min(b[0] for b in selected)
                y0 = min(b[1] for b in selected)
                x1 = max(b[2] for b in selected)
                y1 = max(b[3] for b in selected)
                feature = glyph_feature(arr, (x0, y0, x1, y1), size)
                if feature is None:
                    continue
                vectors.append([round(float(v), 5) for v in feature.tolist()])
                owners.append({"char": char, "font": "actual:" + Path(rel).name})
                added.append(char)
    glyphs["vectors"] = vectors
    glyphs["owners"] = owners
    glyphs["actual_seeds"] = added
    glyphs["note"] = "Windows CJK font renderings plus actual glyphs from the shipped draft frames."
    OUT.write_text(json.dumps(glyphs, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("added actual glyphs", len(added), "unique", len(set(added)))
    print("chars", "".join(sorted(set(added))))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
