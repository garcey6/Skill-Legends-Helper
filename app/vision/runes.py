"""White-rune mask features used as a tie-breaker for same-colour schools."""
from __future__ import annotations

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
    return mask


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
