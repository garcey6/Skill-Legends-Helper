"""Live/replay recognition CLI.

Examples:
    python -m tools.live_recognize --replay samples/frames/draft_001
    python -m tools.live_recognize --image samples/draft_001.png
    python -m tools.live_recognize --live
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kb.recommend import Advisor  # noqa: E402
from app.live.frame import FrameSource  # noqa: E402
from app.live.replaysrc import ImageFrameSource, ReplayFrameSource  # noqa: E402
from app.live.stability import is_still, median_stack  # noqa: E402
from app.live.win32src import WindowFrameSource  # noqa: E402
from app.vision.glyphs import GlyphMatcher  # noqa: E402
from app.vision.ocr import RapidOcrNameMatcher  # noqa: E402
from app.vision.pipeline import build_result, recognize_rois  # noqa: E402
from app.vision.schools import SchoolMatcher  # noqa: E402

LAYOUT_PATH = ROOT / "data" / "recognize" / "layout.json"
SCHOOLS_PATH = ROOT / "data" / "recognize" / "schools_chroma.json"
GLYPHS_PATH = ROOT / "data" / "recognize" / "glyphs.json"
RUNES_PATH = ROOT / "data" / "recognize" / "school_runes.json"


def load_assets(use_ocr: bool = True) -> Dict[str, Any]:
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    schools = json.loads(SCHOOLS_PATH.read_text(encoding="utf-8"))
    glyphs = json.loads(GLYPHS_PATH.read_text(encoding="utf-8"))
    runes = json.loads(RUNES_PATH.read_text(encoding="utf-8")) if RUNES_PATH.exists() else None
    advisor = Advisor()
    names = [h["name"] for h in advisor.heroes]
    return {
        "layout": layout,
        "advisor": advisor,
        "school_matcher": SchoolMatcher(
            schools,
            float(layout.get("margin_min", 0.012)),
            runes=runes,
        ),
        "glyph_matcher": GlyphMatcher(glyphs, names),
        "ocr_matcher": RapidOcrNameMatcher(names) if use_ocr else None,
        "school_by_name": {s["name"]: s["id"] for s in advisor.schools},
    }


def capture_sequence(source: FrameSource, layout: Dict[str, Any], frames: int = 5) -> Dict[str, Any]:
    icons_roi = tuple(layout["rois"]["icons"])
    names_roi = tuple(layout["rois"]["nameplates"])
    icon_frames = []
    name_frames = []
    for _ in range(frames):
        icon = source.grab(icons_roi)
        name = source.grab(names_roi)
        if icon is None or name is None:
            continue
        icon_frames.append(icon.image)
        name_frames.append(name.image)
        time.sleep(float(layout.get("stability", {}).get("frame_interval_ms", 40)) / 1000.0)
    if not icon_frames:
        return {"error": "no frames", "state": source.state().__dict__}
    still, diffs = is_still(icon_frames)
    return {
        "icons": median_stack(icon_frames),
        "nameplates": median_stack(name_frames),
        "stability": {
            "frames_used": len(icon_frames),
            "diff_ratios": [round(v, 4) for v in diffs],
            "still": still,
            "dropped_frames": 0,
            "drop_reasons": [],
        },
        "state": source.state(),
        "frame_id": getattr(source, "frame_id", 0),
    }


def clean_result(
    rec: Dict[str, Any],
    source_name: str,
    frame_id: int = 0,
    state: Any = None,
    stability: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_state = state
    method = getattr(source_state, "capture_method", "none")
    if method == "none":
        method = source_name
    result = {
        "session": {
            "source": source_name,
            "capture_method": method,
            "window": {
                "found": bool(getattr(source_state, "found", True)),
                "client_w": int(getattr(source_state, "client_w", 0)),
                "client_h": int(getattr(source_state, "client_h", 0)),
                "foreground": bool(getattr(source_state, "foreground", False)),
            },
            "state": rec.get("session", {}).get("state", "READY"),
            "frame_id": int(frame_id),
            "scale": rec.get("session", {}).get("scale", 1.0),
        },
        "stability": stability or {},
        "schools": rec["schools"],
        "heroes": {
            "candidates": [
                {
                    "slot": c.get("slot"),
                    "name": c.get("name"),
                    "score": c.get("score", 0.0),
                    "unknown_hero": bool(c.get("unknown_hero")),
                }
                for c in rec["heroes"].get("candidates", [])
            ],
            "glyph_coverage": rec["heroes"].get("glyph_coverage", 0.0),
            "missing_glyphs": rec["heroes"].get("missing_glyphs", []),
        },
        "recommendation": rec.get("recommendation", {"mode": "none", "ranking": [], "global_top5": []}),
        "timings_ms": rec.get("timings_ms", {}),
        "warnings": rec.get("warnings", []),
    }
    if extra:
        result.update(extra)
    return result


def run_replay(path: str, assets: Dict[str, Any], frames: int = 5) -> Dict[str, Any]:
    source = ReplayFrameSource(path)
    seq = capture_sequence(source, assets["layout"], frames)
    if "error" in seq:
        return {"ok": False, "error": seq["error"], "state": str(seq.get("state"))}
    state = seq["state"]
    rec = recognize_rois(
        seq["icons"],
        seq["nameplates"],
        (state.client_w, state.client_h),
        assets["layout"],
        assets["school_matcher"],
        assets["glyph_matcher"],
        assets.get("ocr_matcher"),
    )
    result = build_result(rec, assets["advisor"], assets["school_by_name"])
    return clean_result(result, "replay", seq.get("frame_id", 0), state, seq["stability"], {"ok": True, "replay": path})


def run_image(path: str, assets: Dict[str, Any]) -> Dict[str, Any]:
    source = ImageFrameSource(path)
    seq = capture_sequence(source, assets["layout"], 1)
    state = seq["state"]
    rec = recognize_rois(
        seq["icons"],
        seq["nameplates"],
        (state.client_w, state.client_h),
        assets["layout"],
        assets["school_matcher"],
        assets["glyph_matcher"],
        assets.get("ocr_matcher"),
    )
    result = build_result(rec, assets["advisor"], assets["school_by_name"])
    return clean_result(
        result,
        "image",
        seq.get("frame_id", 0),
        state,
        {"frames_used": 1, "diff_ratios": [], "still": True, "dropped_frames": 0, "drop_reasons": []},
        {"ok": True, "image": path},
    )


def run_live(assets: Dict[str, Any], frames: int = 5) -> Dict[str, Any]:
    source = WindowFrameSource()
    state = source.state()
    if not state.found:
        return {"ok": False, "error": "window_not_found", "state": source.state().__dict__}
    seq = capture_sequence(source, assets["layout"], frames)
    if "error" in seq:
        return {"ok": False, "error": seq["error"], "state": source.state().__dict__}
    rec = recognize_rois(
        seq["icons"],
        seq["nameplates"],
        (state.client_w, state.client_h),
        assets["layout"],
        assets["school_matcher"],
        assets["glyph_matcher"],
        assets.get("ocr_matcher"),
    )
    result = build_result(rec, assets["advisor"], assets["school_by_name"])
    return clean_result(result, "window", seq.get("frame_id", 0), state, seq["stability"], {"ok": True})


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--replay", help="directory of PNG frames + meta.json")
    group.add_argument("--image", help="single screenshot")
    group.add_argument("--live", action="store_true", help="capture the live game window")
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--perf", type=int, default=0, help="repeat N times and report timings")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON output (default)")
    parser.add_argument("--allow-fail", action="store_true")
    args = parser.parse_args()

    assets = load_assets()
    started = time.perf_counter()
    if args.replay:
        result = run_replay(args.replay, assets, args.frames)
    elif args.image:
        result = run_image(args.image, assets)
    else:
        result = run_live(assets, args.frames)
    elapsed = (time.perf_counter() - started) * 1000.0

    if args.perf:
        samples: List[float] = []
        for _ in range(max(1, args.perf)):
            t0 = time.perf_counter()
            if args.replay:
                run_replay(args.replay, assets, args.frames)
            elif args.image:
                run_image(args.image, assets)
            else:
                run_live(assets, args.frames)
            samples.append((time.perf_counter() - t0) * 1000.0)
        samples.sort()
        result["perf"] = {
            "runs": len(samples),
            "mean_ms": round(float(np.mean(samples)), 2),
            "p50_ms": round(float(samples[len(samples) // 2]), 2),
            "p95_ms": round(float(samples[min(len(samples) - 1, int(len(samples) * 0.95))]), 2),
        }
    result["elapsed_ms"] = round(elapsed, 2)

    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    print(text)
    ok = bool(result.get("ok")) and result.get("schools", {}).get("status") == "ok"
    if not ok and not args.allow_fail:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
