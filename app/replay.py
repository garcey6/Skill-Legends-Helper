"""M1 static-image replay.

The live path already depends on ``FrameSource``; this module uses the same
interface for a single image, so tests and the ``python -m app`` entry point do
not need to know anything about window capture.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kb.recommend import Advisor
from app.live.sources import StaticFrameSource
from app.vision.annotation import Annotation, parse_annotation
from app.vision.assets import AssetCache
from app.vision.pipeline import build_result, recognize_rois

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT = ROOT / "data" / "recognize" / "layout.json"
FIXTURES_ROOT = ROOT / "tests" / "fixtures"
FIXTURE_MINIMUM = 10
FIXTURE_TARGET = 10


@dataclass(frozen=True)
class ReplayCase:
    name: str
    image_path: Path
    expected: Dict[str, Any]
    expected_path: Path
    annotation: Optional[Annotation] = None


def load_assets(
    *,
    layout_path: Path = DEFAULT_LAYOUT,
    base_dir: Optional[Path] = None,
    use_ocr: bool = True,
) -> Dict[str, Any]:
    layout = json.loads(Path(layout_path).read_text(encoding="utf-8"))
    advisor = Advisor()
    names = [hero["name"] for hero in advisor.heroes]
    data_dir = Path(base_dir) if base_dir is not None else Path(layout_path).parent
    cache = AssetCache(layout, data_dir, names, use_ocr=use_ocr)
    return {
        "layout": layout,
        "advisor": advisor,
        "cache": cache,
        "school_by_name": {school["name"]: school["id"] for school in advisor.schools},
    }


def discover_cases(fixtures_root: Path = FIXTURES_ROOT) -> List[ReplayCase]:
    expected_dir = Path(fixtures_root) / "expected"
    if not expected_dir.is_dir():
        return []
    cases: List[ReplayCase] = []
    for expected_path in sorted(expected_dir.glob("*.json")):
        payload = json.loads(expected_path.read_text(encoding="utf-8"))
        raw_image = payload.get("image")
        image_path = (
            Path(raw_image)
            if raw_image and Path(raw_image).is_absolute()
            else Path(fixtures_root) / raw_image
            if raw_image
            else Path(fixtures_root) / "screenshots" / (expected_path.stem + ".png")
        )
        image_path = image_path.resolve()
        if not image_path.is_file():
            raise FileNotFoundError("fixture image missing: %s" % image_path)
        cases.append(
            ReplayCase(
                name=expected_path.stem,
                image_path=image_path,
                expected=payload,
                expected_path=expected_path,
                annotation=parse_annotation(payload.get("annotation")),
            )
        )
    return cases


def _annotated_rois(layout: Dict[str, Any], annotation: Optional[Annotation]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    base_icons = tuple(layout["rois"]["icons"])
    base_names = tuple(layout["rois"]["nameplates"])
    if annotation is None:
        return base_icons, base_names
    features = {feature.name: feature.box for feature in annotation.features}
    icons = features.get("icons")
    names = features.get("nameplates")
    if icons is None or names is None:
        return base_icons, base_names

    def as_roi(box: tuple[float, float, float, float]) -> tuple[float, ...]:
        x, y, w, h = box
        return (x, x + w, y, y + h)

    return as_roi(icons), as_roi(names)


def recognize_image(
    path: Path,
    assets: Dict[str, Any] | None = None,
    *,
    annotation: Optional[Annotation] = None,
) -> Dict[str, Any]:
    assets = load_assets() if assets is None else assets
    source = StaticFrameSource(path)
    state = source.state()
    icon_roi, name_roi = _annotated_rois(assets["layout"], annotation)
    icons = source.grab(icon_roi)
    nameplates = source.grab(name_roi)
    if icons is None or nameplates is None:
        raise RuntimeError("static source returned no frame")
    bundle = assets["cache"].for_width(state.client_w)
    recognition = recognize_rois(
        icons.image,
        nameplates.image,
        (state.client_w, state.client_h),
        assets["layout"],
        bundle.school_matcher,
        bundle.glyph_matcher,
        bundle.ocr_matcher,
    )
    result = build_result(recognition, assets["advisor"], assets["school_by_name"])
    candidates = result["heroes"].get("candidates", [])
    return {
        "ok": True,
        "image": str(Path(path).resolve()),
        "width": int(state.client_w),
        "height": int(state.client_h),
        "template_group": bundle.group.to_dict(),
        "heroes": [candidate.get("name") for candidate in candidates],
        "scores": [float(candidate.get("score") or 0.0) for candidate in candidates],
        "schools": result["schools"],
        "recommendation": result["recommendation"],
        "timings_ms": result["timings_ms"],
    }


def run_case(case: ReplayCase, assets: Dict[str, Any] | None = None) -> Dict[str, Any]:
    result = recognize_image(case.image_path, assets, annotation=case.annotation)
    result["name"] = case.name
    return result


def generate_expected(image_path: Path, out_dir: Path) -> Path:
    """Write a draft expected JSON; users correct labels before committing."""
    result = recognize_image(Path(image_path))
    payload = {
        "heroes": result["heroes"],
        "schools": {
            "enabled": list(result["schools"].get("enabled") or []),
            "banned": result["schools"].get("banned"),
        },
        "min_confidence": 0.0,
    }
    target = Path(out_dir) / (Path(image_path).stem + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="M1 static-image replay")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--replay", type=Path, help="single PNG screenshot")
    group.add_argument("--generate-expected", type=Path, help="generate draft fixture JSON")
    parser.add_argument(
        "--out",
        type=Path,
        default=FIXTURES_ROOT / "expected",
        help="directory for --generate-expected",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.generate_expected:
        target = generate_expected(args.generate_expected, args.out)
        print(str(target))
        return 0

    result = recognize_image(args.replay)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
