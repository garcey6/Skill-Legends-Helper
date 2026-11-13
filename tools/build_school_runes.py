"""Build white-rune templates for scheme A (colour + rune tie-break)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.blobs import segment_runs  # noqa: E402
from app.vision.runes import rune_feature, rune_template  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "recognize" / "school_runes.json"
IDS = ["basic", "dodge", "crit", "life", "heal", "ultimate", "poison", "freeze", "shield", "vulnerable", "spirit", "rage", "haste"]


def main() -> int:
    icons = DATA / "templates" / "schools"
    layout = json.loads((DATA / "recognize" / "layout.json").read_text(encoding="utf-8"))
    templates = []
    for sid in IDS:
        path = icons / (sid + ".png")
        vector = rune_template(Image.open(path))
        templates.append({"id": sid, "vectors": [[round(float(v), 5) for v in vector.tolist()]] if vector is not None else []})
    by_id = {item["id"]: item for item in templates}
    variants = [
        ("samples/draft_001.png", ["basic", "heal", "ultimate", "poison", "shield", "spirit", "rage", "haste"]),
        ("samples/window_draft.png", ["dodge", "crit", "heal", "ultimate", "freeze", None, "rage", "haste"]),
    ]
    for rel, labels in variants:
        path = ROOT / rel
        if not path.exists():
            continue
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
        h, w = arr.shape[:2]
        x0, x1, y0, y1 = layout["rois"]["icons"]
        icons_arr = arr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
        runs = segment_runs(icons_arr, (0, 1, 0, 1), layout["sat_th"], layout["min_run_w"])
        if len(runs) != 8:
            continue
        cy = int(np.median([r["cy"] for r in runs]))
        for run, sid in zip(runs, labels):
            if not sid or sid not in by_id:
                continue
            half = max(4, int(run["w"] * 0.55))
            vec = rune_feature(icons_arr, int(run["cx"]), cy, half)
            if vec is None:
                continue
            rounded = [round(float(v), 5) for v in vec.tolist()]
            if rounded not in by_id[sid]["vectors"]:
                by_id[sid]["vectors"].append(rounded)
    payload = {"version": 1, "size": 24, "source": "panel icons + clean bottom icons", "templates": templates}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("wrote", OUT)
    for item in templates:
        print(item["id"], len(item["vectors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
