"""White-rune mask features used as a tie-breaker for same-colour schools."""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
from PIL import Image

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

SIZE = 24


def _normalize(mask: np.ndarray) -> Optional[np.ndarray]:
    if mask is None or mask.size == 0:
        return None
    ys, xs = np.nonzero(mask)
    if len(ys) < 8:
        return None
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    if cv2 is not None:
        resized = cv2.resize(crop.astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST)
    else:
        resized = np.asarray(
            Image.fromarray(crop.astype(np.uint8) * 255).resize((SIZE, SIZE), Image.NEAREST)
        ) > 127
    vec = resized.astype(np.float32)
    vec -= vec.mean()
    std = float(vec.std())
    if std < 1e-6:
        return None
    return (vec / std).reshape(-1)


def _fallback_component(mask: np.ndarray) -> Optional[np.ndarray]:
    """Pick the central non-border component without OpenCV.

    The cv2 path filters the page edge and keeps the compact white rune; this
    pure-numpy fallback does the same so rune tie-break also works when cv2 is
    not installed (the project's runtime only requires the three base deps).
    """
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best_score = -1.0
    best_pixels: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            queue = deque([(y, x)])
            seen[y, x] = True
            pixels: list[tuple[int, int]] = []
            touches = False
            while queue:
                cy, cx = queue.popleft()
                pixels.append((cy, cx))
                if cy == 0 or cx == 0 or cy == h - 1 or cx == w - 1:
                    touches = True
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(pixels) < 8:
                continue
            ys = [p[0] for p in pixels]
            xs = [p[1] for p in pixels]
            center_dist = abs(sum(xs) / len(xs) - w / 2.0) / max(1, w) + abs(
                sum(ys) / len(ys) - h / 2.0
            ) / max(1, h)
            score = len(pixels) * (0.15 if touches else 1.0) * (1.0 - min(0.8, center_dist))
            if score > best_score:
                best_score = score
                best_pixels = pixels
    if not best_pixels:
        return None
    component = np.zeros_like(mask, dtype=np.uint8)
    for y, x in best_pixels:
        component[y, x] = 1
    return component


def _white_mask(arr: np.ndarray, center: float = 0.72) -> Optional[np.ndarray]:
    if arr.size == 0:
        return None
    h, w = arr.shape[:2]
    m = int(min(h, w) * (1.0 - center) / 2.0)
    sub = arr[m:h - m, m:w - m].astype(np.int16)
    if sub.size == 0:
        return None
    lum = sub.mean(axis=2)
    sat = sub.max(axis=2) - sub.min(axis=2)
    mask = ((lum > 185) & (sat < 55)).astype(np.uint8)
    if int(mask.sum()) < 8:
        return None
    if cv2 is not None:
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        if count <= 1:
            return None
        h2, w2 = mask.shape
        candidates = []
        for index in range(1, count):
            x, y, ww, hh, area = stats[index]
            touches_border = x <= 0 or y <= 0 or x + ww >= w2 or y + hh >= h2
            cx, cy = centroids[index]
            center_dist = abs(cx - w2 / 2.0) / max(1, w2) + abs(cy - h2 / 2.0) / max(1, h2)
            if area < 8:
                continue
            # The page edge is a large white component touching the crop border;
            # the rune is the compact white symbol near the centre.
            score = area * (1.0 if not touches_border else 0.15) * (1.0 - min(0.8, center_dist))
            candidates.append((score, index))
        if not candidates:
            return None
        best = max(candidates)[1]
        return (labels == best).astype(np.uint8)
    return _fallback_component(mask)


def rune_feature(arr: np.ndarray, cx: int, cy: int, half: int) -> Optional[np.ndarray]:
    h, w = arr.shape[:2]
    x0, x1 = max(0, cx - half), min(w, cx + half + 1)
    y0, y1 = max(0, cy - half), min(h, cy + half + 1)
    return _normalize(_white_mask(arr[y0:y1, x0:x1]))


def rune_template(image: Image.Image) -> Optional[np.ndarray]:
    return _normalize(_white_mask(np.asarray(image.convert("RGB"), dtype=np.int16), 0.82))


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    den = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / den) if den > 1e-9 else 0.0
