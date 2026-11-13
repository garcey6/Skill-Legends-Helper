"""Report school-match margins across replay frames for threshold calibration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.blobs import segment_runs  # noqa: E402
from app.vision.chroma import chroma  # noqa: E402
from app.vision.schools import SchoolMatcher  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", required=True)
    args = parser.parse_args()
    base = Path(args.replay)
    if not base.is_absolute():
        base = ROOT / base
    layout = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "data" / "recognize" / "schools_chroma.json").read_text(encoding="utf-8"))
    matcher = SchoolMatcher(data, float(layout.get("margin_min", 0.012)))
    all_margins = []
    files = sorted(base.glob("*.png"))
    for path in files:
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
        h, w = arr.shape[:2]
        x0, x1, y0, y1 = layout["rois"]["icons"]
        icons = arr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
        runs = segment_runs(icons, (0, 1, 0, 1), layout["sat_th"], layout["min_run_w"])
        if len(runs) != 8:
            continue
        scale = float(np.median([r["w"] for r in runs])) / layout["base_run_w"]
        cy = int(np.median([r["cy"] for r in runs]))
        half = max(4, int(round(layout["base_half"] * scale)))
        vectors = [chroma(icons, int(r["cx"]), cy, half) for r in runs]
        result = matcher.match(vectors)
        all_margins.extend(float(v) for v in result.get("margins", []) if v)
    if not all_margins:
        print("no usable frames")
        return 2
    arr = np.asarray(all_margins)
    print(json.dumps({
        "frames": len(files),
        "samples": int(arr.size),
        "min": round(float(arr.min()), 4),
        "p05": round(float(np.percentile(arr, 5)), 4),
        "median": round(float(np.median(arr)), 4),
        "current_margin_min": layout.get("margin_min"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
