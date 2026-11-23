"""Build a read-only debug frame from one recognition result.

The normal recognition path does not pay for this module.  The agent only
calls :func:`build_debug_frame` while the debug overlay is explicitly enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DebugBox:
    """One rectangle in client pixels plus its human-readable label."""

    x: int
    y: int
    w: int
    h: int
    label: str = ""
    score: float = 0.0
    kind: str = ""

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "label": self.label,
            "score": round(float(self.score), 4),
            "kind": self.kind,
        }


@dataclass(frozen=True)
class DebugFrame:
    timestamp: str
    image_size: Tuple[int, int]
    rois: Tuple[DebugBox, ...]
    ocr: Tuple[DebugBox, ...]
    templates: Tuple[DebugBox, ...]
    timings_ms: Dict[str, float]
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "image_size": list(self.image_size),
            "rois": [box.to_dict() for box in self.rois],
            "ocr": [box.to_dict() for box in self.ocr],
            "templates": [box.to_dict() for box in self.templates],
            "timings_ms": dict(self.timings_ms),
            "failure_reason": self.failure_reason,
        }


def _roi_box(roi: Sequence[float], size: Tuple[int, int], label: str) -> DebugBox:
    x0, x1, y0, y1 = (float(v) for v in roi)
    w, h = size
    x = int(round(x0 * w))
    y = int(round(y0 * h))
    return DebugBox(
        x=x,
        y=y,
        w=max(1, int(round((x1 - x0) * w))),
        h=max(1, int(round((y1 - y0) * h))),
        label=label,
        kind="roi",
    )


def _fallback_plate(index: int, count: int, roi: Sequence[float], size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Approximate a nameplate slot when OCR did not expose its rectangle."""
    x0, x1, y0, y1 = (float(v) for v in roi)
    w, h = size
    total = max(1, int(round((x1 - x0) * w)))
    slot_w = max(1, total // max(1, count))
    x = int(round(x0 * w)) + index * slot_w
    return (x, int(round(y0 * h)), x + slot_w, int(round(y1 * h)))


def _box_from_plate(box: Sequence[int], size: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
    if len(box) < 4:
        return None
    x0, y0, x1, y1 = (int(round(float(v))) for v in box[:4])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _roi_origin(roi: Sequence[float], size: Tuple[int, int]) -> Tuple[int, int]:
    x0, _x1, y0, _y1 = (float(v) for v in roi)
    return (int(round(x0 * size[0])), int(round(y0 * size[1])))


def _offset_box(
    box: Sequence[int], origin: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (x0 + origin[0], y0 + origin[1], x1 + origin[0], y1 + origin[1])


def build_debug_frame(
    recognition: Mapping[str, Any],
    layout: Mapping[str, Any],
    client_size: Tuple[int, int],
    *,
    timestamp: Optional[str] = None,
) -> DebugFrame:
    """Convert a pipeline result into a drawable, serializable frame.

    ``client_size`` is the size of the screenshot the boxes refer to.  The
    recognition result already carries ``runs``, ``glyph_boxes`` and usually
    ``plate_boxes``; no pixel work is done here.
    """
    size = (max(1, int(client_size[0])), max(1, int(client_size[1])))
    rois_cfg = layout.get("rois") or {}
    rois: List[DebugBox] = []
    for key, label in (("icons", "图标条"), ("nameplates", "英雄名牌")):
        roi = rois_cfg.get(key)
        if roi and len(roi) == 4:
            rois.append(_roi_box(roi, size, label))

    heroes = recognition.get("heroes") or {}
    candidates = list(heroes.get("candidates") or [])
    plate_boxes = list(recognition.get("plate_boxes") or [])
    name_roi = rois_cfg.get("nameplates") or (0.0, 1.0, 0.0, 1.0)
    name_origin = _roi_origin(name_roi, size)
    ocr: List[DebugBox] = []
    for index, cand in enumerate(candidates):
        slot = int(cand.get("slot", index))
        box = None
        if slot < len(plate_boxes):
            box = _box_from_plate(plate_boxes[slot], size)
            if box is not None:
                box = _offset_box(box, name_origin)
        if box is None:
            box = _fallback_plate(index, max(1, len(candidates)), name_roi, size)
        x0, y0, x1, y1 = box
        name = cand.get("name")
        ocr.append(
            DebugBox(
                x=x0,
                y=y0,
                w=max(1, x1 - x0),
                h=max(1, y1 - y0),
                label=str(name) if name else "未识别",
                score=float(cand.get("score") or 0.0),
                kind=str(cand.get("source") or "ocr"),
            )
        )

    schools = recognition.get("schools") or {}
    status = str(schools.get("status") or "unknown")
    enabled = list(schools.get("enabled") or [])
    margins = list(schools.get("margins") or [])
    icon_roi = rois_cfg.get("icons") or (0.0, 0.0, 0.0, 0.0)
    icon_origin = _roi_origin(icon_roi, size)
    templates: List[DebugBox] = []
    for index, run in enumerate(recognition.get("runs") or []):
        try:
            x0 = int(round(float(run.get("x0", 0))))
            x1 = int(round(float(run.get("x1", x0))))
            cy = float(run.get("cy", 0.0))
            w = int(round(float(run.get("w", x1 - x0))))
        except (TypeError, ValueError):
            continue
        h = max(8, w)
        label = str(enabled[index]) if status == "ok" and index < len(enabled) else "未标注"
        score = 0.0
        if index < len(margins):
            try:
                score = float(margins[index])
            except (TypeError, ValueError):
                score = 0.0
        templates.append(
            DebugBox(
                x=x0 + icon_origin[0],
                y=int(round(cy - h / 2.0)) + icon_origin[1],
                w=max(1, w),
                h=h,
                label=label,
                score=score,
                kind="template",
            )
        )

    warnings = [str(item) for item in recognition.get("warnings") or [] if str(item)]
    reasons: List[str] = []
    if status != "ok":
        reasons.append("流派识别 %s" % status)
    reasons.extend(warnings)
    stamp = timestamp or datetime.now().astimezone().isoformat(timespec="seconds")
    timings: Dict[str, float] = {}
    for key, value in (recognition.get("timings_ms") or {}).items():
        try:
            timings[str(key)] = round(float(value), 2)
        except (TypeError, ValueError):
            continue
    return DebugFrame(
        timestamp=stamp,
        image_size=size,
        rois=tuple(rois),
        ocr=tuple(ocr),
        templates=tuple(templates),
        timings_ms=timings,
        failure_reason="；".join(reasons),
    )
