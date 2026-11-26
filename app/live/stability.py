"""Frame stability helpers: diff ratio and median aggregation."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

import numpy as np

Rect = Tuple[int, int, int, int]


def diff_ratio(a: np.ndarray, b: np.ndarray, threshold: int = 24) -> float:
    if a.shape != b.shape:
        return 1.0
    return float(np.mean(np.max(np.abs(a.astype(np.int16) - b.astype(np.int16)), axis=2) > threshold))


def diff_ratio_masked(
    a: np.ndarray,
    b: np.ndarray,
    rects: Sequence[Rect] | None = None,
    threshold: int = 24,
) -> float:
    """Like diff_ratio, but ignores pixels covered by overlay rectangles.

    The HUD can overlap the icon strip while a probe is grabbed.  The last
    accepted strip is clean (captured with the HUD hidden), so comparing the
    overlap area would trigger a new capture burst on every loop and make the
    HUD blink.  Rectangles are in ROI-local pixel coordinates.
    """
    if a.shape != b.shape:
        return 1.0
    if not rects:
        return diff_ratio(a, b, threshold)
    height, width = a.shape[:2]
    mask = np.ones((height, width), dtype=bool)
    for x0, y0, x1, y1 in rects:
        x0 = max(0, min(width, int(x0)))
        y0 = max(0, min(height, int(y0)))
        x1 = max(0, min(width, int(x1)))
        y1 = max(0, min(height, int(y1)))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = False
    if not mask.any():
        return 0.0
    diff = np.max(np.abs(a.astype(np.int16) - b.astype(np.int16)), axis=2) > threshold
    return float(np.mean(diff[mask]))


def roi_overlap_rects(
    roi: Tuple[float, float, float, float],
    client_size: Tuple[int, int],
    client_origin: Tuple[int, int],
    overlay: Rect,
) -> List[Rect]:
    """Intersect a normalized ROI with a screen-space overlay rectangle.

    Returns ROI-local rectangles suitable for diff_ratio_masked.
    """
    client_w, client_h = max(0, int(client_size[0])), max(0, int(client_size[1]))
    if client_w <= 0 or client_h <= 0:
        return []
    rx0, rx1, ry0, ry1 = roi
    left = int(round(rx0 * client_w))
    top = int(round(ry0 * client_h))
    right = int(round(rx1 * client_w))
    bottom = int(round(ry1 * client_h))
    ox, oy = int(client_origin[0]), int(client_origin[1])
    screen_left, screen_top = ox + left, oy + top
    screen_right, screen_bottom = ox + right, oy + bottom
    hx0, hy0, hx1, hy1 = overlay
    ix0 = max(screen_left, int(hx0))
    iy0 = max(screen_top, int(hy0))
    ix1 = min(screen_right, int(hx1))
    iy1 = min(screen_bottom, int(hy1))
    if ix1 <= ix0 or iy1 <= iy0:
        return []
    return [(ix0 - screen_left, iy0 - screen_top, ix1 - screen_left, iy1 - screen_top)]


def median_stack(frames: List[np.ndarray]) -> np.ndarray:
    return np.median(np.stack(frames, axis=0), axis=0).astype(np.uint8)


def is_still(frames: List[np.ndarray], threshold: int = 24, ratio: float = 0.02, k: int = 3) -> Tuple[bool, List[float]]:
    if len(frames) < 2:
        return False, []
    diffs = [diff_ratio(frames[i], frames[i - 1], threshold) for i in range(1, len(frames))]
    recent = diffs[-k:] if len(diffs) >= k else diffs
    return bool(recent and all(value < ratio for value in recent)), diffs


def drop_cursor_frames(frames: List[np.ndarray]) -> Tuple[List[np.ndarray], List[str]]:
    """Very small pointer heuristic: a near-white moving component in a frame.

    Full pointer shape detection is deliberately conservative; median stacking
    does most of the work.  A frame is only dropped when a bright compact blob
    is present in a minority of frames.
    """
    if len(frames) < 3:
        return frames, []
    masks = []
    for frame in frames:
        lum = frame.mean(axis=2)
        masks.append(lum > 235)
    counts = np.asarray([int(mask.sum()) for mask in masks])
    median_count = float(np.median(counts))
    kept: List[np.ndarray] = []
    reasons: List[str] = []
    for frame, count, mask in zip(frames, counts, masks):
        if count > max(median_count + 80, 240):
            reasons.append("cursor_detected")
            continue
        kept.append(frame)
    return (kept or frames), reasons
