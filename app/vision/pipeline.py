"""Live recognition pipeline: ROI arrays -> schools + hero names + result.

This module is intentionally free of disk and GDI access.  The CLI/agent owns
loading templates and the frame source; tests can feed arrays directly.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .blobs import group_nameplates, segment_glyphs, segment_runs
from .chroma import chroma
from .runes import rune_feature


def recognize_rois(
    icons: np.ndarray,
    nameplates: np.ndarray,
    client_size: Tuple[int, int],
    layout: Dict[str, Any],
    school_matcher: Any,
    glyph_matcher: Any,
    ocr_matcher: Any = None,
) -> Dict[str, Any]:
    """Recognize one median-stacked frame from its two ROI crops."""
    started = time.perf_counter()
    client_w, client_h = int(client_size[0]), int(client_size[1])
    expected = int(layout.get("expected_enabled", 8))
    runs = segment_runs(
        icons,
        (0.0, 1.0, 0.0, 1.0),
        sat_th=int(layout.get("sat_th", 40)),
        min_width=max(8, int(float(layout.get("min_run_w", 20)) * client_w / 1800.0)),
    )
    scale = 1.0
    if runs:
        width = float(np.median([r["w"] for r in runs]))
        scale = width / max(1.0, float(layout.get("base_run_w", 55.0)))
    half = max(4, int(round(float(layout.get("base_half", 15.0)) * scale)))
    cy = int(np.median([r["cy"] for r in runs])) if runs else int(icons.shape[0] * 0.5)

    schools: Dict[str, Any]
    if len(runs) != expected:
        schools = {
            "status": "failed",
            "confidence": "none",
            "enabled": [],
            "banned": None,
            "margins": [],
            "margin_min": float(layout.get("margin_min", 0.012)),
            "suspect_slots": [],
            "run_count": len(runs),
        }
    else:
        vectors = [chroma(icons, int(r["cx"]), cy, half) for r in runs]
        rune_half = max(8, int(float(np.median([r["w"] for r in runs])) * 0.55))
        rune_vectors = [rune_feature(icons, int(r["cx"]), cy, rune_half) for r in runs]
        schools = school_matcher.match(vectors, rune_vectors)
        schools["run_count"] = len(runs)
    school_ms = (time.perf_counter() - started) * 1000.0

    started_hero = time.perf_counter()
    boxes: List[Any] = []
    if ocr_matcher is not None:
        heroes = ocr_matcher.match(nameplates, client_w, glyph_matcher)
    else:
        boxes = segment_glyphs(
            nameplates,
            (0.0, 1.0, 0.0, 1.0),
            bright_percentile=float(layout.get("glyphs", {}).get("bright_percentile", 72)),
            min_area_scale=float(layout.get("glyphs", {}).get("min_area_scale", 80)),
            min_height_px=max(8, int(client_h * 0.025)),
        )
        groups = group_nameplates(
            boxes,
            gap_threshold=client_w * 0.035,
            client_height=client_h,
            max_names=5,
        )
        heroes = glyph_matcher.match(nameplates, groups)
    hero_ms = (time.perf_counter() - started_hero) * 1000.0

    warnings: List[str] = []
    if len(runs) != expected:
        warnings.append("图标条 run 数 %d，预期 %d" % (len(runs), expected))
    if schools.get("status") != "ok":
        warnings.append("流派识别未达 ok：%s" % schools.get("status"))
    for cand in heroes.get("candidates", []):
        if not cand.get("name"):
            warnings.append("英雄槽位 %s 未识别" % (cand.get("slot") + 1))

    return {
        "session": {"source": "roi", "state": "READY", "scale": round(scale, 4)},
        "schools": schools,
        "heroes": heroes,
        "warnings": warnings,
        "timings_ms": {
            "schools": round(school_ms, 2),
            "heroes": round(hero_ms, 2),
            "total": round((time.perf_counter() - started) * 1000.0, 2),
        },
        "runs": runs,
        "glyph_boxes": boxes,
    }


def build_result(
    recognition: Dict[str, Any],
    advisor: Any,
    school_by_name: Dict[str, str],
    top_global: int = 5,
) -> Dict[str, Any]:
    """Attach the existing explainable recommendation to a recognition result."""
    schools = recognition.get("schools", {})
    heroes = recognition.get("heroes", {})
    names = [c.get("name") for c in heroes.get("candidates", []) if c.get("name")]
    enabled_names = list(schools.get("enabled") or [])
    banned_names = schools.get("banned") or []
    recommendation: Dict[str, Any] = {"mode": "none", "ranking": [], "global_top5": []}
    enabled_ids = [school_by_name[n] for n in enabled_names if n in school_by_name]
    banned_ids = [school_by_name[n] for n in banned_names if n in school_by_name]
    if schools.get("status") == "ok" and names and len(enabled_ids) == 8 and len(banned_ids) == 5:
        rec = advisor.recommend(names, enabled_ids, banned_ids)
        ranking = [
            {"name": card["name"], "points": round(float(card["score"]), 1)}
            for card in rec.get("recommendations", [])
        ]
        recommendation = {"mode": "full", "ranking": ranking, "global_top5": []}
    elif schools.get("status") == "partial" and names:
        # No banned set is known.  Do not invent one and do not apply ban
        # penalties; rank only against the confident enabled subset.
        ranked = []
        for name in names:
            hero, _matched = advisor.resolve_hero(name)
            if hero is None:
                continue
            scored = advisor.score_hero(hero, enabled_ids, [])
            ranked.append({"name": hero["name"], "points": round(float(scored["score"]), 1)})
        ranked.sort(key=lambda item: item["points"], reverse=True)
        recommendation = {"mode": "no_ban_penalty", "ranking": ranked, "global_top5": []}
    if not recommendation["global_top5"] and getattr(advisor, "heroes", None):
        top = sorted(advisor.heroes, key=lambda h: float(h.get("power", 0)), reverse=True)[:top_global]
        recommendation["global_top5"] = [[h["name"], round(float(h.get("power", 0)), 1)] for h in top]
    return {
        "session": recognition.get("session", {}),
        "schools": schools,
        "heroes": heroes,
        "recommendation": recommendation,
        "timings_ms": recognition.get("timings_ms", {}),
        "warnings": recognition.get("warnings", []),
    }
