"""RapidOCR hero-name regression tests (skipped when OCR is unavailable)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from app.vision.glyphs import GlyphMatcher
from app.vision.ocr import RapidOcrNameMatcher

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
GLYPHS = json.loads((ROOT / "data" / "recognize" / "glyphs.json").read_text(encoding="utf-8"))
HEROES = [h["name"] for h in json.loads((ROOT / "data" / "heroes.json").read_text(encoding="utf-8"))["heroes"]]


class OcrNameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matcher = RapidOcrNameMatcher(HEROES)
        if not cls.matcher.available:
            raise unittest.SkipTest("rapidocr_onnxruntime unavailable: %s" % cls.matcher.error)
        cls.glyph = GlyphMatcher(GLYPHS, HEROES)

    def _names(self, path: Path):
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
        h, w = arr.shape[:2]
        x0, x1, y0, y1 = LAYOUT["rois"]["nameplates"]
        crop = arr[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
        result = self.matcher.match(crop, w, self.glyph)
        return [c.get("name") for c in result["candidates"]], result

    def test_sample_and_window(self) -> None:
        names, result = self._names(ROOT / "samples" / "draft_001.png")
        self.assertEqual(names, ["森林游侠", "神秘法师", "魔镜"])
        self.assertGreaterEqual(result["glyph_coverage"], 0.0)
        names, _ = self._names(ROOT / "samples" / "window_draft.png")
        self.assertEqual(names, ["守财奴", "狂暴战将", "精灵牧师"])

    def test_new_window_cases(self) -> None:
        for filename, expected in [
            ("case01_client.png", ["矮人领主", "皇家骑士", "熊猫武士"]),
            ("case02_client.png", ["狂暴战将", "霜影暴君", "神秘法师"]),
        ]:
            names, _ = self._names(ROOT / "samples" / "validation" / filename)
            self.assertEqual(names, expected, filename)


if __name__ == "__main__":
    unittest.main()
