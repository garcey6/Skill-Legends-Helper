"""Regression tests for the live ROI recognizer (no game window needed)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from app.kb.recommend import Advisor
from app.live.stability import diff_ratio, is_still, median_stack
from app.vision.blobs import segment_runs
from app.vision.chroma import chroma
from app.vision.glyphs import GlyphMatcher
from app.vision.pipeline import build_result, recognize_rois
from app.vision.runes import rune_feature
from app.vision.schools import SchoolMatcher

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
SCHOOLS = json.loads((ROOT / "data" / "recognize" / "schools_chroma.json").read_text(encoding="utf-8"))
GLYPHS = json.loads((ROOT / "data" / "recognize" / "glyphs.json").read_text(encoding="utf-8"))


class LiveRecognitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.advisor = Advisor()
        cls.school_matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        cls.glyph_matcher = GlyphMatcher(GLYPHS, [h["name"] for h in cls.advisor.heroes])
        cls.school_by_name = {s["name"]: s["id"] for s in cls.advisor.schools}

    def _rois(self, path: Path):
        image = Image.open(path).convert("RGB")
        arr = np.asarray(image, dtype=np.uint8)
        h, w = arr.shape[:2]
        icons = LAYOUT["rois"]["icons"]
        names = LAYOUT["rois"]["nameplates"]
        return (
            arr[int(h * icons[2]):int(h * icons[3]), int(w * icons[0]):int(w * icons[1])],
            arr[int(h * names[2]):int(h * names[3]), int(w * names[0]):int(w * names[1])],
            (w, h),
        )

    def _recognize(self, path: Path):
        icons, names, size = self._rois(path)
        return recognize_rois(icons, names, size, LAYOUT, self.school_matcher, self.glyph_matcher)

    def test_sample_pipeline(self) -> None:
        rec = self._recognize(ROOT / "samples" / "draft_001.png")
        self.assertEqual(rec["schools"]["status"], "ok")
        self.assertEqual(
            rec["schools"]["enabled"],
            ["普攻流", "回复流", "大招流", "中毒流", "护盾流", "精灵流", "怒气流", "急速流"],
        )
        self.assertEqual(
            rec["schools"]["banned"], ["闪避流", "暴击流", "生命流", "冰冻流", "易伤流"]
        )
        self.assertEqual(
            [c["name"] for c in rec["heroes"]["candidates"]],
            ["森林游侠", "神秘法师", "魔镜"],
        )
        result = build_result(rec, self.advisor, self.school_by_name)
        self.assertEqual(result["recommendation"]["mode"], "full")
        self.assertEqual(len(result["recommendation"]["ranking"]), 3)

    def test_window_pipeline(self) -> None:
        rec = self._recognize(ROOT / "samples" / "window_draft.png")
        self.assertEqual(rec["schools"]["status"], "ok")
        self.assertEqual(
            rec["schools"]["enabled"],
            ["闪避流", "暴击流", "回复流", "大招流", "冰冻流", "精灵流", "怒气流", "急速流"],
        )
        self.assertEqual(
            rec["schools"]["banned"], ["普攻流", "生命流", "中毒流", "护盾流", "易伤流"]
        )
        self.assertEqual(
            [c["name"] for c in rec["heroes"]["candidates"]],
            ["守财奴", "狂暴战将", "精灵牧师"],
        )

    def test_rune_tiebreak_resolves_life(self) -> None:
        runes_path = ROOT / "data" / "recognize" / "school_runes.json"
        if not runes_path.exists():
            self.skipTest("rune templates missing")
        runes = json.loads(runes_path.read_text(encoding="utf-8"))
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)), runes=runes)
        for filename in ("case01_client.png", "case02_client.png"):
            arr = np.asarray(
                Image.open(ROOT / "samples" / "validation" / filename).convert("RGB"),
                dtype=np.uint8,
            )
            h, w = arr.shape[:2]
            icons = LAYOUT["rois"]["icons"]
            crop = arr[int(h * icons[2]):int(h * icons[3]), int(w * icons[0]):int(w * icons[1])]
            runs = segment_runs(crop, (0, 1, 0, 1), LAYOUT["sat_th"], LAYOUT["min_run_w"])
            self.assertEqual(len(runs), 8)
            scale = float(np.median([r["w"] for r in runs])) / LAYOUT["base_run_w"]
            half = max(4, int(LAYOUT["base_half"] * scale))
            rh = max(8, int(np.median([r["w"] for r in runs]) * 0.55))
            cy = int(np.median([r["cy"] for r in runs]))
            vectors = [chroma(crop, int(r["cx"]), cy, half) for r in runs]
            rune_vectors = [rune_feature(crop, int(r["cx"]), cy, rh) for r in runs]
            result = matcher.match(vectors, rune_vectors)
            self.assertEqual(result["status"], "ok", filename)
            self.assertIn("生命流", result["enabled"], filename)
            self.assertTrue(result.get("rune_used"), filename)

    def test_wrong_run_count_is_failed(self) -> None:
        icons = np.zeros((200, 600, 3), dtype=np.uint8)
        names = np.zeros((200, 600, 3), dtype=np.uint8)
        rec = recognize_rois(icons, names, (1800, 1118), LAYOUT, self.school_matcher, self.glyph_matcher)
        self.assertEqual(rec["schools"]["status"], "failed")
        self.assertIsNone(rec["schools"]["banned"])

    def test_median_and_stability(self) -> None:
        a = np.zeros((20, 20, 3), dtype=np.uint8)
        b = a + 100
        self.assertGreater(diff_ratio(a, b, 24), 0.9)
        stack = median_stack([a, a, b])
        self.assertEqual(int(stack[0, 0, 0]), 0)
        still, diffs = is_still([a, a, a], threshold=24, ratio=0.02, k=3)
        self.assertTrue(still)
        self.assertEqual(diffs, [0.0, 0.0])

    def test_replay_cli_module(self) -> None:
        from tools.live_recognize import run_replay

        result = run_replay(str(ROOT / "samples" / "frames" / "draft_002"), {
            "layout": LAYOUT,
            "advisor": self.advisor,
            "school_matcher": self.school_matcher,
            "glyph_matcher": self.glyph_matcher,
            "school_by_name": self.school_by_name,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["schools"]["status"], "ok")
        self.assertEqual(
            [c["name"] for c in result["heroes"]["candidates"]],
            ["守财奴", "狂暴战将", "精灵牧师"],
        )


if __name__ == "__main__":
    unittest.main()
