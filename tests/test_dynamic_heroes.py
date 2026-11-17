"""Dynamic hero-count regression tests for OCR and glyph fallback."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from app.vision.glyphs import GlyphMatcher
from app.vision.ocr import RapidOcrNameMatcher

ROOT = Path(__file__).resolve().parent.parent
GLYPHS = json.loads((ROOT / "data" / "recognize" / "glyphs.json").read_text(encoding="utf-8"))
NAMES = ["森林游侠", "神秘法师", "魔镜", "守财奴", "狂暴战将", "精灵牧师"]


class FakeGlyph:
    def match(self, arr, groups, trim_trailing=True):
        return {"candidates": [], "glyph_coverage": 1.0, "missing_glyphs": []}


class FakeOcr(RapidOcrNameMatcher):
    def __init__(self, texts):
        super().__init__(NAMES)
        self.texts = list(texts)

    @property
    def available(self):
        return True

    @property
    def error(self):
        return ""

    def detect_plates(self, arr, client_w):
        return [(0, 0, 80, 40)] * len(self.texts)

    def _ocr_crop(self, crop):
        return self.texts.pop(0) if self.texts else ("", 0.0)


def names_for(texts):
    result = FakeOcr(texts).match(np.zeros((80, 400, 3), np.uint8), 1800, FakeGlyph())
    return [c["name"] for c in result["candidates"]]


class DynamicHeroTest(unittest.TestCase):
    def test_five_stone_plates_are_detected(self) -> None:
        from PIL import Image

        from app.vision.ocr import RapidOcrNameMatcher

        arr = np.asarray(Image.open(ROOT / "samples" / "draft_001.png").convert("RGB"), dtype=np.uint8)
        h, w = arr.shape[:2]
        layout = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
        x0, x1, y0, y1 = layout["rois"]["nameplates"]
        crop = arr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
        plates = RapidOcrNameMatcher(NAMES).detect_plates(crop, w)
        self.assertEqual(len(plates), 5)

    def test_three_heroes_stop_at_special(self) -> None:
        self.assertEqual(
            names_for(
                [
                    ("森林游侠", 0.99),
                    ("神秘法师", 0.99),
                    ("魔镜", 0.99),
                    ("特权解锁", 0.99),
                    ("随机", 0.99),
                ]
            ),
            ["森林游侠", "神秘法师", "魔镜"],
        )

    def test_four_heroes(self) -> None:
        self.assertEqual(
            names_for(
                [
                    ("森林游侠", 0.99),
                    ("神秘法师", 0.99),
                    ("魔镜", 0.99),
                    ("守财奴", 0.99),
                    ("特权解锁", 0.99),
                ]
            ),
            ["森林游侠", "神秘法师", "魔镜", "守财奴"],
        )

    def test_one_hero(self) -> None:
        self.assertEqual(names_for([("森林游侠", 0.99), ("随机", 0.99)]), ["森林游侠"])

    def test_ocr_failure_keeps_slot(self) -> None:
        self.assertEqual(
            names_for([("森林游侠", 0.99), ("", 0.0), ("魔镜", 0.99), ("随机", 0.99)]),
            ["森林游侠", None, "魔镜"],
        )

    def test_misread_special_plate_stops(self) -> None:
        self.assertEqual(names_for([("森林游侠", 0.99), ("特权解", 0.99), ("随机", 0.99)]), ["森林游侠"])

    def test_glyph_fallback_is_not_padded_to_three(self) -> None:
        matcher = GlyphMatcher(GLYPHS, NAMES)

        def fake_match_nameplate(_arr, _boxes):
            return {"name": "森林游侠", "score": 1.0, "top": []}

        matcher.match_nameplate = fake_match_nameplate  # type: ignore[method-assign]
        groups = [[(0, 0, 5, 5, 10)] for _ in range(4)]
        result = matcher.match(np.zeros((80, 400, 3), np.uint8), groups)
        self.assertEqual(len(result["candidates"]), 4)

    def test_glyph_keeps_trailing_unknown_when_ocr_boundary_known(self) -> None:
        matcher = GlyphMatcher(GLYPHS, NAMES)
        calls = {"count": 0}

        def fake_match_nameplate(_arr, _boxes):
            calls["count"] += 1
            name = "森林游侠" if calls["count"] < 4 else None
            return {"name": name, "score": 1.0 if name else 0.0, "top": []}

        matcher.match_nameplate = fake_match_nameplate  # type: ignore[method-assign]
        groups = [[(0, 0, 5, 5, 10)] for _ in range(4)]
        result = matcher.match(
            np.zeros((80, 400, 3), np.uint8),
            groups,
            trim_trailing=False,
        )
        self.assertEqual(len(result["candidates"]), 4)
        self.assertIsNone(result["candidates"][3]["name"])


if __name__ == "__main__":
    unittest.main()
