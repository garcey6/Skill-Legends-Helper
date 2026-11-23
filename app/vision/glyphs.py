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
    # Full-name fallback thresholds.  These are raw 16x16 template dot scores,
    # averaged over the name's characters.  The values are calibrated against
    # every real fixture: real names score above 147, while the special
    # “特权解锁/随机” plates top out near 115.  Keep the margin requirement so
    # the fallback cannot turn a near-tie into a confident wrong answer.
    FULL_NAME_MIN_SCORE = 130.0
    FULL_NAME_MIN_MARGIN = 20.0

    def __init__(self, data: Dict[str, Any], names: List[str]) -> None:
        self.size = int(data.get("size", 16))
        self.top_k = 5
        self.chars = list(data.get("chars", []))
        self.vectors = np.asarray(data.get("vectors", []), dtype=np.float32)
        owners = data.get("owners", [])
        self.owners = owners
        self.template_chars = [str(o.get("char", "")) for o in owners] if owners else self.chars
        self._by_char: Dict[str, List[int]] = {}
        for index, char in enumerate(self.template_chars):
            self._by_char.setdefault(char, []).append(index)
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

    @staticmethod
    def _merge_fragments(boxes: List[Box]) -> List[Box]:
        """Merge top/bottom pieces and inner fragments of one character.

        Thin or dim outlines split a CJK glyph into several 4-connected
        components.  Pieces whose x ranges overlap by at least half of the
        narrower box belong to the same character.
        """
        merged: List[Box] = []
        for box in sorted(boxes, key=lambda item: (item[0], item[1])):
            x0, y0, x1, y1, area = box
            for index, (mx0, my0, mx1, my1, marea) in enumerate(merged):
                overlap = min(x1, mx1) - max(x0, mx0)
                narrow = min(x1 - x0, mx1 - mx0)
                if overlap > 0 and narrow > 0 and overlap >= 0.5 * narrow:
                    merged[index] = (
                        min(x0, mx0),
                        min(y0, my0),
                        max(x1, mx1),
                        max(y1, my1),
                        area + marea,
                    )
                    break
            else:
                merged.append(box)
        return merged

    def _fallback_name(
        self, arr: np.ndarray, boxes: List[Box]
    ) -> Optional[Dict[str, Any]]:
        """Rank complete names by the best template score for every character.

        The legacy top-5 gate is deliberately conservative: a character that
        is visually close to several templates can rank below the fifth slot
        and veto an otherwise obvious name.  This fallback keeps the same
        segment partitions and closed-set names, but scores a name by the raw
        template similarity of each character, then requires both an absolute
        score and a margin over the runner-up.
        """
        if self.vectors.size == 0:
            return None
        ranked: List[Tuple[float, str]] = []
        for n in (2, 3, 4, 5):
            if n not in self.by_len or len(boxes) < n:
                continue
            for partition in _partitions(len(boxes), n):
                groups: List[List[Box]] = []
                cursor = 0
                for take in partition:
                    groups.append(boxes[cursor:cursor + take])
                    cursor += take
                char_scores: List[Dict[str, float]] = []
                for group in groups:
                    x0 = min(b[0] for b in group)
                    y0 = min(b[1] for b in group)
                    x1 = max(b[2] for b in group)
                    y1 = max(b[3] for b in group)
                    feature = glyph_feature(arr, (x0, y0, x1, y1), self.size)
                    if feature is None:
                        char_scores = []
                        break
                    scores = self.vectors @ feature
                    char_scores.append(
                        {
                            char: float(scores[indexes].max())
                            for char, indexes in self._by_char.items()
                        }
                    )
                if len(char_scores) != n:
                    continue
                for name in self.by_len[n]:
                    if not all(char in char_map for char, char_map in zip(name, char_scores)):
                        continue
                    score = sum(
                        char_map[char] for char, char_map in zip(name, char_scores)
                    ) / n
                    ranked.append((score, name))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        unique: List[Tuple[float, str]] = []
        seen = set()
        for score, name in ranked:
            if name in seen:
                continue
            seen.add(name)
            unique.append((score, name))
        top_score, top_name = unique[0]
        if top_score < self.FULL_NAME_MIN_SCORE:
            return None
        if len(unique) > 1 and top_score - unique[1][0] < self.FULL_NAME_MIN_MARGIN:
            return None
        scale = float(self.size * self.size)
        return {
            "name": top_name,
            "score": round(top_score / scale, 4),
            "top": [name for _, name in unique[:5]],
            "raw_score": round(top_score, 4),
            "fallback": True,
        }

    def match_nameplate(self, arr: np.ndarray, boxes: List[Box]) -> Dict[str, Any]:
        if not boxes:
            return {"name": None, "score": 0.0, "top": []}
        boxes = self._merge_fragments(boxes)
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
            fallback = self._fallback_name(arr, boxes)
            if fallback is not None:
                return fallback
            return {"name": None, "score": 0.0, "top": []}
        best.sort(key=lambda item: item[0], reverse=True)
        top_score = best[0][0]
        tied = [item for item in best if abs(item[0] - top_score) < 1e-6]
        unique = {name for _, name, _ in tied}
        if len(unique) != 1:
            fallback = self._fallback_name(arr, boxes)
            if fallback is not None:
                return fallback
            return {"name": None, "score": 0.0, "top": best[0][2], "ambiguous": True}
        score, name, top = best[0]
        return {"name": name, "score": round(float(score), 4), "top": top}

    def match(
        self,
        arr: np.ndarray,
        groups: List[List[Box]],
        trim_trailing: bool = True,
    ) -> Dict[str, Any]:
        candidates = []
        missing: List[str] = []
        for index, group in enumerate(groups[:5]):
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
        # The OCR-less legacy path cannot read 特权解锁/随机; trailing unknowns
        # there are usually those two special slots.  The OCR path already
        # knows the hero boundary and passes trim_trailing=False.
        if trim_trailing:
            while candidates and not candidates[-1].get("name"):
                candidates.pop()
        return {
            "candidates": candidates,
            "glyph_coverage": self.coverage,
            "missing_glyphs": missing,
        }
