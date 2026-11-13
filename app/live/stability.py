"""Frame stability helpers: diff ratio and median aggregation."""
from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np


def diff_ratio(a: np.ndarray, b: np.ndarray, threshold: int = 24) -> float:
    if a.shape != b.shape:
        return 1.0
    return float(np.mean(np.max(np.abs(a.astype(np.int16) - b.astype(np.int16)), axis=2) > threshold))


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
