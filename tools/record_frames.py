"""Record full-client frames for offline replay/calibration.

The live pipeline only needs two ROIs, but replay fixtures keep full frames so
the ROI layout can be recalibrated later.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live.win32src import _find_title_window  # noqa: E402
from app.overlay import capture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--interval-ms", type=int, default=40)
    parser.add_argument("--enabled", default="")
    parser.add_argument("--banned", default="")
    parser.add_argument("--heroes", default="")
    args = parser.parse_args()

    capture.enable_dpi_awareness()
    hwnd = _find_title_window()
    if not hwnd:
        print("no title-matching game window")
        return 2
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "client_w": 0,
        "client_h": 0,
        "enabled": [s for s in args.enabled.split(",") if s],
        "banned": [s for s in args.banned.split(",") if s],
        "heroes": [s for s in args.heroes.split(",") if s],
        "frames": [],
    }
    for index in range(max(1, args.frames)):
        started = time.time()
        shot = capture.capture(hwnd=hwnd)
        name = "frame_%03d.png" % index
        shot.image.save(out / name)
        meta["client_w"], meta["client_h"] = shot.image.size
        meta["frames"].append(
            {
                "file": name,
                "client_w": shot.image.width,
                "client_h": shot.image.height,
                "timestamp": started,
                "method": shot.method,
            }
        )
        time.sleep(max(0.0, args.interval_ms / 1000.0))
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out, "frames", len(meta["frames"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
