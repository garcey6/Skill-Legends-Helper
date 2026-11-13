"""Closed-set hero-name matching from nameplate glyphs.

No general OCR: each segmented glyph is compared with a 16x16 template library
of the 155 characters used by the 60 hero names.  A nameplate is split into
2..5 character groups, and a hero name is accepted only when every character is
in that glyph's top-k candidates and exactly one name wins.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

Box = Tuple[int, int, int, int, int]


def _normalize(image: Image.Image, size: int) -> Optional[np.ndarray]:
    image = image.convert("L")
    array = np.asarray(image, dtype=np.float32)
    array -= float(array.mean())
    std = float(array.std())
    if std < 1e-6:
        return None
    return (array / std).reshape(-1)


def glyph_feature(arr: np.ndarray, box: Sequence[int], size: int, percentile: float = 72.0) -> Optional[np.ndarray]:
    x0, y0, x1, y1 = [int(v) for v in box[:4]]
    h, w = arr.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    crop = arr[y0:y1, x0:x1].astype(np.int16)
    lum = crop.mean(axis=2)
    mask = lum >= max(float(np.percentile(lum, percentile)), 180.0)
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    image = Image.fromarray(lum.astype(np.uint8), "L").crop(
        (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    )
    image = image.resize((size, size), Image.LANCZOS)
    return _normalize(image, size)


def _partitions(count: int, parts: int) -> Iterable[Tuple[int, ...]]:
    if parts <= 0 or parts > count:
        return
    if parts == 1:
        yield (count,)
        return
    for first in range(1, count - parts + 2):
        for rest in _partitions(count - first, parts - 1):
            yield (first,) + rest


class GlyphMatcher:
    def __init__(self, data: Dict[str, Any], names: List[str]) -> None:
        self.size = int(data.get("size", 16))
        self.top_k = 5
        self.chars = list(data.get("chars", []))
        self.vectors = np.asarray(data.get("vectors", []), dtype=np.float32)
        owners = data.get("owners", [])
        self.owners = owners
        self.template_chars = [str(o.get("char", "")) for o in owners] if owners else self.chars
        self.names = [n for n in names if 2 <= len(n) <= 5]
        self.by_len: Dict[int, List[str]] = {}
        for name in self.names:
            self.by_len.setdefault(len(name), []).append(name)
        self.coverage = float(data.get("coverage", 0.0))
        self.missing_glyphs: List[str] = []

    def _top_chars(self, feature: np.ndarray) -> List[str]:
        if self.vectors.size == 0:
            return []
        scores = self.vectors @ feature
        order = np.argsort(scores)[::-1]
        out: List[str] = []
        for idx in order:
            ch = self.template_chars[int(idx)]
            if ch not in out:
                out.append(ch)
            if len(out) >= self.top_k:
                break
        return out

    def match_nameplate(self, arr: np.ndarray, boxes: List[Box]) -> Dict[str, Any]:
        if not boxes:
            return {"name": None, "score": 0.0, "top": []}
        boxes = sorted(boxes, key=lambda b: b[0])
        best: List[Tuple[float, str, List[List[str]]]] = []
        for n in (2, 3, 4, 5):
            if n not in self.by_len or len(boxes) < n:
                continue
            for partition in _partitions(len(boxes), n):
                groups: List[List[Box]] = []
                cursor = 0
                for take in partition:
                    groups.append(boxes[cursor:cursor + take])
                    cursor += take
                features: List[np.ndarray] = []
                group_boxes: List[Tuple[int, int, int, int]] = []
                for group in groups:
                    x0 = min(b[0] for b in group)
                    y0 = min(b[1] for b in group)
                    x1 = max(b[2] for b in group)
                    y1 = max(b[3] for b in group)
                    feature = glyph_feature(arr, (x0, y0, x1, y1), self.size)
                    if feature is None:
                        features = []
                        break
                    features.append(feature)
                    group_boxes.append((x0, y0, x1, y1))
                if len(features) != n:
                    continue
                top = [self._top_chars(f) for f in features]
                for name in self.by_len[n]:
                    if not all(ch in candidates for ch, candidates in zip(name, top)):
                        continue
                    rank_score = 0.0
                    for ch, candidates in zip(name, top):
                        rank = candidates.index(ch)
                        rank_score += 1.0 if rank == 0 else (0.75 if rank < 3 else 0.5)
                    best.append((rank_score / n, name, top))
        if not best:
            return {"name": None, "score": 0.0, "top": []}
        best.sort(key=lambda item: item[0], reverse=True)
        top_score = best[0][0]
        tied = [item for item in best if abs(item[0] - top_score) < 1e-6]
        unique = {name for _, name, _ in tied}
        if len(unique) != 1:
            return {"name": None, "score": 0.0, "top": best[0][2], "ambiguous": True}
        score, name, top = best[0]
        return {"name": name, "score": round(float(score), 4), "top": top}

    def match(self, arr: np.ndarray, groups: List[List[Box]]) -> Dict[str, Any]:
        candidates = []
        missing: List[str] = []
        for index, group in enumerate(groups[:3]):
            result = self.match_nameplate(arr, group)
            name = result.get("name")
            candidates.append(
                {
                    "slot": index,
                    "name": name,
                    "score": round(float(result.get("score", 0.0)), 4),
                    "unknown_hero": bool(name and name not in self.names),
                }
            )
        while len(candidates) < 3:
            candidates.append(
                {"slot": len(candidates), "name": None, "score": 0.0, "unknown_hero": False}
            )
        return {
            "candidates": candidates,
            "glyph_coverage": self.coverage,
            "missing_glyphs": missing,
        }
