"""Run the current recognizer on the user-provided validation cases."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.live_recognize import load_assets, run_image  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 when hero labels do not match")
    args = parser.parse_args()
    base = ROOT / "samples" / "validation"
    meta = json.loads((base / "meta.json").read_text(encoding="utf-8"))
    assets = load_assets()
    failed = False
    for case in meta["cases"]:
        path = base / case["client"]
        result = run_image(str(path), assets)
        actual = [c.get("name") for c in result.get("heroes", {}).get("candidates", [])]
        expected = case["expected"]["heroes"]
        matches = [a == e for a, e in zip(actual, expected)]
        if not all(matches):
            failed = True
        print(
            json.dumps(
                {
                    "case": case["name"],
                    "expected_heroes": expected,
                    "actual_heroes": actual,
                    "hero_slots_ok": matches,
                    "schools_status": result.get("schools", {}).get("status"),
                    "schools_enabled": result.get("schools", {}).get("enabled"),
                    "schools_suspect_slots": result.get("schools", {}).get("suspect_slots"),
                },
                ensure_ascii=False,
            )
        )
    return 1 if (args.strict and failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
