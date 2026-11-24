"""Normalized fixture annotations for cross-resolution replay.

The canonical label source is ``tests/fixtures/expected/*.json``.  An optional
``annotation`` block stores feature rectangles in 0..1 coordinates plus the
base resolution used while drawing them.  Runtime code can therefore scale the
same annotation to any screenshot size without a second label tree.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PIL import Image


class AnnotationError(ValueError):
    """Raised when an annotation payload is malformed or out of bounds."""


Box = Tuple[float, float, float, float]
PixelBox = Tuple[int, int, int, int]


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnnotationError("%s must be a number" % field) from exc
    if not number == number or number in (float("inf"), float("-inf")):
        raise AnnotationError("%s must be finite" % field)
    return number


def normalize_rect(rect: PixelBox, width: int, height: int) -> Box:
    """Convert a pixel ``(x, y, w, h)`` rectangle to normalized coordinates."""
    if width <= 0 or height <= 0:
        raise AnnotationError("base resolution must be positive")
    x, y, w, h = (int(value) for value in rect)
    if w <= 0 or h <= 0:
        raise AnnotationError("feature rectangle must have positive size")
    if x < 0 or y < 0 or x + w > width or y + h > height:
        raise AnnotationError("feature rectangle is outside the screenshot")
    return (x / width, y / height, w / width, h / height)


def scale_rect(box: Box, width: int, height: int) -> PixelBox:
    """Scale a normalized rectangle to pixel coordinates for one screenshot."""
    if width <= 0 or height <= 0:
        raise AnnotationError("target resolution must be positive")
    x, y, w, h = box
    left = int(round(x * width))
    top = int(round(y * height))
    box_w = max(1, int(round(w * width)))
    box_h = max(1, int(round(h * height)))
    if left < 0 or top < 0 or left + box_w > width or top + box_h > height:
        raise AnnotationError("scaled rectangle is outside the screenshot")
    return (left, top, box_w, box_h)


@dataclass(frozen=True)
class Feature:
    name: str
    box: Box

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise AnnotationError("feature name must not be empty")
        if len(self.box) != 4:
            raise AnnotationError("feature box must have four values")
        x, y, w, h = self.box
        for value in (x, y, w, h):
            if not 0.0 <= float(value) <= 1.0:
                raise AnnotationError("normalized box values must be within 0..1")
        if w <= 0.0 or h <= 0.0:
            raise AnnotationError("normalized box must have positive size")
        if x + w > 1.0 + 1e-9 or y + h > 1.0 + 1e-9:
            raise AnnotationError("normalized box exceeds the screenshot")

    def to_pixels(self, width: int, height: int) -> PixelBox:
        return scale_rect(self.box, width, height)


@dataclass(frozen=True)
class Annotation:
    base_resolution: Tuple[int, int]
    features: Tuple[Feature, ...]

    def __post_init__(self) -> None:
        width, height = self.base_resolution
        if width <= 0 or height <= 0:
            raise AnnotationError("base resolution must be positive")
        if not self.features:
            raise AnnotationError("annotation must contain at least one feature")
        names = [feature.name for feature in self.features]
        if len(names) != len(set(names)):
            raise AnnotationError("feature names must be unique")
        for feature in self.features:
            feature.to_pixels(width, height)

    @classmethod
    def from_rects(
        cls,
        base_resolution: Tuple[int, int],
        rects: Mapping[str, PixelBox],
    ) -> "Annotation":
        width, height = base_resolution
        return cls(
            base_resolution=(int(width), int(height)),
            features=tuple(
                Feature(name, normalize_rect(rect, width, height))
                for name, rect in rects.items()
            ),
        )

    def to_pixels(self, width: int, height: int) -> Dict[str, PixelBox]:
        return {feature.name: feature.to_pixels(width, height) for feature in self.features}

    def to_dict(self) -> Dict[str, Any]:
        width, height = self.base_resolution
        return {
            "base_resolution": {"width": width, "height": height},
            "features": [
                {"name": feature.name, "box": [round(value, 6) for value in feature.box]}
                for feature in self.features
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Annotation":
        try:
            base = payload["base_resolution"]
            width = int(base["width"])
            height = int(base["height"])
            raw_features = payload["features"]
        except (KeyError, TypeError, ValueError) as exc:
            raise AnnotationError("invalid annotation payload") from exc
        if not isinstance(raw_features, Sequence) or isinstance(raw_features, (str, bytes)):
            raise AnnotationError("features must be a list")
        features = []
        for raw in raw_features:
            if not isinstance(raw, Mapping):
                raise AnnotationError("feature must be an object")
            try:
                name = str(raw["name"])
                box = raw["box"]
            except KeyError as exc:
                raise AnnotationError("feature must contain name and box") from exc
            if not isinstance(box, Sequence) or isinstance(box, (str, bytes)) or len(box) != 4:
                raise AnnotationError("feature box must have four values")
            features.append(
                Feature(name, tuple(_number(value, "box") for value in box))  # type: ignore[arg-type]
            )
        return cls(base_resolution=(width, height), features=tuple(features))


def parse_annotation(payload: Any) -> Optional[Annotation]:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise AnnotationError("annotation must be an object")
    return Annotation.from_dict(payload)


def update_expected_annotation(path: Path, annotation: Annotation) -> Dict[str, Any]:
    """Merge an annotation into an existing fixture JSON using an atomic write."""
    destination = Path(path)
    payload: Dict[str, Any] = {}
    if destination.is_file():
        payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["annotation"] = annotation.to_dict()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + ".", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return payload


def image_size(path: Path) -> Tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def annotation_for_image(
    path: Path,
    rects: Mapping[str, PixelBox],
) -> Annotation:
    width, height = image_size(path)
    return Annotation.from_rects((width, height), rects)
