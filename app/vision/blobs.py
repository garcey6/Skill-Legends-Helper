"""Connected components and ROI segmentation for the live recognizer.

Kept dependency-free (numpy only) so the live path works without scipy; the
4-connected implementation is used for nameplate glyphs, where 8-connectivity
would merge adjacent outlined characters.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Sequence, Tuple

import numpy as np

Box = Tuple[int, int, int, int]


def _components_4(mask: np.ndarray, min_area: int) -> List[Tuple[int, int, int, int, int]]:
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out: List[Tuple[int, int, int, int, int]] = []
    for y0 in range(h):
        row = mask[y0]
        for x0 in range(w):
            if not row[x0] or seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            minx = maxx = x0
            miny = maxy = y0
            area = 0
            while stack:
                y, x = stack.pop()
                area += 1
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
                if x > 0 and mask[y, x - 1] and not seen[y, x - 1]:
                    seen[y, x - 1] = True
                    stack.append((y, x - 1))
                if x + 1 < w and mask[y, x + 1] and not seen[y, x + 1]:
                    seen[y, x + 1] = True
                    stack.append((y, x + 1))
                if y > 0 and mask[y - 1, x] and not seen[y - 1, x]:
                    seen[y - 1, x] = True
                    stack.append((y - 1, x))
                if y + 1 < h and mask[y + 1, x] and not seen[y + 1, x]:
                    seen[y + 1, x] = True
                    stack.append((y + 1, x))
            if area >= min_area:
                out.append((minx, miny, maxx + 1, maxy + 1, area))
    return out


def segment_runs(
    arr: np.ndarray,
    roi: Sequence[float],
    sat_th: int = 40,
    min_width: int = 12,
    col_threshold: int = 2,
) -> List[Dict[str, float]]:
    """Find the tilted-book runs in the bottom icon strip ROI.

    ROI is ``(x0, x1, y0, y1)`` in relative 0..1 units.
    """
    h, w = arr.shape[:2]
    x0, x1, y0, y1 = roi
    px0, px1 = int(w * x0), int(w * x1)
    py0, py1 = int(h * y0), int(h * y1)
    sub = arr[py0:py1, px0:px1].astype(np.int16)
    if sub.size == 0:
        return []
    sat = sub.max(axis=2) - sub.min(axis=2)
    cols = (sat > sat_th).sum(axis=0)
    runs: List[Dict[str, float]] = []
    start = None
    for i, value in enumerate(cols.tolist() + [0]):
        if value > col_threshold and start is None:
            start = i
        elif value <= col_threshold and start is not None:
            if i - start >= min_width:
                a, b = px0 + start, px0 + i
                ys, xs = np.nonzero(sat[:, start:i] > sat_th)
                if len(ys):
                    cy = py0 + float(ys.mean())
                    runs.append({"x0": a, "x1": b, "cx": (a + b - 1) / 2.0, "cy": cy, "w": b - a})
            start = None
    return runs


def segment_glyphs(
    arr: np.ndarray,
    roi: Sequence[float],
    bright_percentile: float = 72.0,
    min_area_scale: float = 80.0,
    min_height_ratio: float = 0.025,
    min_height_px: int = 0,
) -> List[Tuple[int, int, int, int, int]]:
    """4-connected bright components inside a nameplate ROI.

    Returns absolute ``(x0, y0, x1, y1, area)`` boxes.
    """
    h, w = arr.shape[:2]
    x0, x1, y0, y1 = roi
    px0, px1 = int(w * x0), int(w * x1)
    py0, py1 = int(h * y0), int(h * y1)
    sub = arr[py0:py1, px0:px1].astype(np.int16)
    if sub.size == 0:
        return []
    lum = sub.mean(axis=2)
    threshold = max(float(np.percentile(lum, bright_percentile)), 180.0)
    mask = lum > threshold
    area_min = max(20, int(min_area_scale * (w / 1800.0) ** 2))
    boxes = _components_4(mask, area_min)
    min_h = max(8, int(min_height_px or h * min_height_ratio))
    out = []
    for a, b, c, d, area in boxes:
        if (d - b) >= min_h:
            out.append((a + px0, b + py0, c + px0, d + py0, area))
    out.sort(key=lambda item: item[0])
    return out


def group_nameplates(
    boxes: Sequence[Tuple[int, int, int, int, int]],
    gap_threshold: float,
    client_height: int,
    max_names: int = 5,
) -> List[List[Tuple[int, int, int, int, int]]]:
    """Group glyph boxes into nameplate names.

    First keep the dominant horizontal text band (nameplates share one y band);
    this rejects stray white UI elements and school-panel text.  Then split by
    large x gaps.
    """
    if not boxes:
        return []
    y_tol = max(10.0, client_height * 0.03)
    clusters: List[List[Tuple[int, int, int, int, int]]] = []
    for box in sorted(boxes, key=lambda item: (item[1] + item[3]) / 2.0):
        cy = (box[1] + box[3]) / 2.0
        for cluster in clusters:
            cluster_cy = sum((b[1] + b[3]) / 2.0 for b in cluster) / len(cluster)
            if abs(cy - cluster_cy) <= y_tol:
                cluster.append(box)
                break
        else:
            clusters.append([box])
    if not clusters:
        return []
    cluster = max(clusters, key=lambda c: sum(b[4] for b in c))
    groups: List[List[Tuple[int, int, int, int, int]]] = []
    for box in sorted(cluster, key=lambda item: (item[0], item[1])):
        if groups and box[0] - groups[-1][-1][2] <= gap_threshold:
            groups[-1].append(box)
        else:
            groups.append([box])
    groups = [g for g in groups if len(g) >= 2]
    return groups[:max_names]
