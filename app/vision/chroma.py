"""Color-chroma feature used by the live school matcher.

The value is brightness/gamma invariant: it is the mean of the saturated
pixels inside a square window, divided by its channel sum.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


def chroma(arr: np.ndarray, cx: int, cy: int, half: int) -> Optional[np.ndarray]:
    if half < 1:
        return None
    h, w = arr.shape[:2]
    x0 = max(0, cx - half)
    x1 = min(w, cx + half + 1)
    y0 = max(0, cy - half)
    y1 = min(h, cy + half + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    win = arr[y0:y1, x0:x1].astype(np.float32)
    sat = win.max(axis=2) - win.min(axis=2)
    px = win[sat > 35]
    if len(px) < 8:
        return None
    mean = px.mean(axis=0)
    total = float(mean.sum())
    if total <= 1e-6:
        return None
    return mean / total
