"""Color-chroma school matcher with one-to-one assignment and margins."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


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
    def __init__(self, data: Dict[str, Any], margin_min: float = 0.012) -> None:
        self.templates = list(data.get("templates", []))
        self.ids = [str(item["id"]) for item in self.templates]
        self.names = {str(item["id"]): str(item.get("name", item["id"])) for item in self.templates}
        self.vectors = np.asarray([item["chroma"] for item in self.templates], dtype=np.float32)
        self.variant_vectors: List[List[np.ndarray]] = []
        for item in self.templates:
            variants = item.get("variants") or [item["chroma"]]
            self.variant_vectors.append([np.asarray(v, dtype=np.float32) for v in variants])
        self.margin_min = float(margin_min)

    def _distances(self, vector: np.ndarray) -> np.ndarray:
        return np.asarray(
            [
                min(float(np.linalg.norm(np.asarray(v, dtype=np.float32) - vector)) for v in variants)
                for variants in self.variant_vectors
            ],
            dtype=np.float64,
        )

    def match(self, vecs: Sequence[Optional[np.ndarray]]) -> Dict[str, Any]:
        count = len(vecs)
        valid = [(i, v) for i, v in enumerate(vecs) if v is not None]
        if count == 0 or not valid:
            return {"status": "failed", "confidence": "none", "enabled": [], "banned": None, "margins": [], "suspect_slots": []}

        # 8 slots -> 13 template columns; 5 dummy rows absorb unused schools.
        rows = len(self.vectors)
        cost = np.zeros((rows, rows), dtype=np.float64)
        for slot, vector in valid:
            cost[slot, :] = self._distances(vector)
        assignment = _hungarian(cost)

        assigned: List[Tuple[int, str, float, float]] = []
        suspect: List[int] = []
        margins: List[float] = []
        for slot in range(count):
            vector = vecs[slot]
            if vector is None:
                suspect.append(slot)
                margins.append(0.0)
                continue
            j = assignment[slot]
            if j < 0:
                suspect.append(slot)
                margins.append(0.0)
                continue
            distances = self._distances(vector)
            alt = min(float(distances[k]) for k in range(rows) if k != j)
            margin = alt - float(distances[j])
            margins.append(round(margin, 4))
            if margin < self.margin_min:
                suspect.append(slot)
            assigned.append((slot, self.ids[j], float(distances[j]), margin))

        # Keep only confident slots for partial output.
        confident = [sid for slot, sid, _, _ in assigned if slot not in suspect]
        if len(confident) == len(vecs) and not suspect:
            banned_ids = [sid for sid in self.ids if sid not in set(confident)]
            return {
                "status": "ok",
                "confidence": "high",
                "enabled": [self.names[sid] for sid in confident],
                "banned": [self.names[sid] for sid in banned_ids],
                "margins": margins,
                "margin_min": self.margin_min,
                "suspect_slots": [],
            }
        return {
            "status": "partial" if confident else "failed",
            "confidence": "low" if confident else "none",
            "enabled": [self.names[sid] for sid in confident],
            "banned": None,
            "margins": margins,
            "margin_min": self.margin_min,
            "suspect_slots": sorted(set(suspect)),
        }
