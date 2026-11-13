"""Color-chroma school matcher with one-to-one assignment and margins."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .runes import ncc


def _hungarian(cost: np.ndarray) -> List[int]:
    """Minimum-cost assignment for a square/rectangular (n<=m) matrix."""
    n, m = cost.shape
    if n > m:
        raise ValueError("cost rows must be <= columns")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [1e18] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = 1e18
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = float(cost[i0 - 1, j - 1]) - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [-1] * n
    for j in range(1, m + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


class SchoolMatcher:
    def __init__(
        self,
        data: Dict[str, Any],
        margin_min: float = 0.012,
        runes: Optional[Dict[str, Any]] = None,
        rune_weight: float = 0.03,
    ) -> None:
        self.templates = list(data.get("templates", []))
        self.ids = [str(item["id"]) for item in self.templates]
        self.names = {str(item["id"]): str(item.get("name", item["id"])) for item in self.templates}
        self.vectors = np.asarray([item["chroma"] for item in self.templates], dtype=np.float32)
        self.variant_vectors: List[List[np.ndarray]] = []
        for item in self.templates:
            variants = item.get("variants") or [item["chroma"]]
            self.variant_vectors.append([np.asarray(v, dtype=np.float32) for v in variants])
        self.margin_min = float(margin_min)
        self.rune_weight = float(rune_weight)
        self.rune_variants: List[List[np.ndarray]] = []
        rune_by_id: Dict[str, List[np.ndarray]] = {}
        if runes:
            for item in runes.get("templates", []):
                rune_by_id[str(item["id"])] = [
                    np.asarray(v, dtype=np.float32) for v in item.get("vectors", [])
                ]
        for sid in self.ids:
            self.rune_variants.append(rune_by_id.get(sid, []))

    def _distances(self, vector: np.ndarray) -> np.ndarray:
        return np.asarray(
            [
                min(float(np.linalg.norm(np.asarray(v, dtype=np.float32) - vector)) for v in variants)
                for variants in self.variant_vectors
            ],
            dtype=np.float64,
        )

    def _evaluate(self, cost: np.ndarray, count: int, margins_from_cost: bool = True) -> Dict[str, Any]:
        assignment = _hungarian(cost)
        assigned: List[Tuple[int, str, float, float]] = []
        suspect: List[int] = []
        margins: List[float] = []
        for slot in range(count):
            j = assignment[slot]
            if j < 0:
                suspect.append(slot)
                margins.append(0.0)
                continue
            distances = cost[slot]
            alt = min(float(distances[k]) for k in range(cost.shape[1]) if k != j)
            margin = alt - float(distances[j])
            margins.append(round(margin, 4))
            if margin < self.margin_min:
                suspect.append(slot)
            assigned.append((slot, self.ids[j], float(distances[j]), margin))

        confident = [sid for slot, sid, _, _ in assigned if slot not in suspect]
        slot_ids = [None] * count
        for slot, sid, _, _ in assigned:
            slot_ids[slot] = sid
        if len(confident) == count and not suspect:
            banned_ids = [sid for sid in self.ids if sid not in set(confident)]
            return {
                "status": "ok",
                "confidence": "high",
                "enabled": [self.names[sid] for sid in confident],
                "banned": [self.names[sid] for sid in banned_ids],
                "margins": margins,
                "margin_min": self.margin_min,
                "suspect_slots": [],
                "slot_ids": slot_ids,
            }
        return {
            "status": "partial" if confident else "failed",
            "confidence": "low" if confident else "none",
            "enabled": [self.names[sid] for sid in confident],
            "banned": None,
            "margins": margins,
            "margin_min": self.margin_min,
            "suspect_slots": sorted(set(suspect)),
            "slot_ids": slot_ids,
        }

    def _rune_cost(self, rune_vecs: Optional[Sequence[Optional[np.ndarray]]]) -> Optional[np.ndarray]:
        if not rune_vecs or not any(self.rune_variants):
            return None
        rows = len(self.vectors)
        cost = np.ones((rows, rows), dtype=np.float64)
        for slot, vec in enumerate(rune_vecs):
            if vec is None or slot >= rows:
                continue
            for j, variants in enumerate(self.rune_variants):
                if variants:
                    cost[slot, j] = 1.0 - max(ncc(vec, variant) for variant in variants)
        return cost

    def match(
        self,
        vecs: Sequence[Optional[np.ndarray]],
        rune_vecs: Optional[Sequence[Optional[np.ndarray]]] = None,
    ) -> Dict[str, Any]:
        count = len(vecs)
        valid = [(i, v) for i, v in enumerate(vecs) if v is not None]
        if count == 0 or not valid:
            return {"status": "failed", "confidence": "none", "enabled": [], "banned": None, "margins": [], "suspect_slots": []}

        # 8 slots -> 13 template columns; 5 dummy rows absorb unused schools.
        rows = len(self.vectors)
        color_cost = np.zeros((rows, rows), dtype=np.float64)
        for slot, vector in valid:
            color_cost[slot, :] = self._distances(vector)
        base = self._evaluate(color_cost, count)
        if base["status"] == "ok":
            return base
        rune_cost = self._rune_cost(rune_vecs)
        if rune_cost is None:
            return base
        # Scheme A: only when colour is ambiguous, use the white-rune match to
        # resolve the suspect slots.  A rune must beat the runner-up by a clear
        # margin; otherwise the colour result stays partial.
        slot_ids = list(base.get("slot_ids") or [])
        suspect_set = set(base.get("suspect_slots", []))
        used = {sid for slot, sid in enumerate(slot_ids) if sid and slot not in suspect_set}
        resolved = True
        rune_margins: List[float] = []
        for slot in base.get("suspect_slots", []):
            scores = [(1.0 - float(rune_cost[slot, j]), self.ids[j]) for j in range(len(self.ids))]
            scores.sort(reverse=True)
            if len(scores) < 2:
                resolved = False
                break
            best_score, best_id = scores[0]
            second_score, _ = scores[1]
            if best_id in used or best_score < 0.35 or best_score - second_score < 0.05:
                resolved = False
                break
            slot_ids[slot] = best_id
            used.add(best_id)
            rune_margins.append(round(best_score - second_score, 4))
        if resolved and all(slot_ids) and len(used) == count:
            enabled_ids = [slot_ids[i] for i in range(count)]
            banned_ids = [sid for sid in self.ids if sid not in set(enabled_ids)]
            result = {
                "status": "ok",
                "confidence": "high",
                "enabled": [self.names[sid] for sid in enabled_ids],
                "banned": [self.names[sid] for sid in banned_ids],
                "margins": base.get("margins", []),
                "margin_min": self.margin_min,
                "suspect_slots": [],
                "rune_used": True,
                "rune_margins": rune_margins,
                "slot_ids": slot_ids,
            }
            return result
        base["rune_used"] = False
        return base
