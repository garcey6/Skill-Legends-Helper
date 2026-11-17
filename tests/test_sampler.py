"""Live sampler stability tests."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

import numpy as np

from app.kb.recommend import Advisor
from app.live.replaysrc import ImageFrameSource
from app.live.sampler import LiveSampler, consistent_frames
from app.vision.glyphs import GlyphMatcher
from app.vision.schools import SchoolMatcher

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
SCHOOLS = json.loads((ROOT / "data" / "recognize" / "schools_chroma.json").read_text(encoding="utf-8"))
GLYPHS = json.loads((ROOT / "data" / "recognize" / "glyphs.json").read_text(encoding="utf-8"))


class SamplerTest(unittest.TestCase):
    def test_consistent_frames_drops_ragged_shape(self) -> None:
        good = np.zeros((10, 20, 3), dtype=np.uint8)
        bad = np.zeros((11, 20, 3), dtype=np.uint8)
        self.assertEqual(len(consistent_frames([good, bad, good])), 2)

    def test_static_source_pushes_once(self) -> None:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        events = []
        sampler = LiveSampler(
            ImageFrameSource(ROOT / "samples" / "draft_001.png"),
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: events.append((state, result)),
            interval_ms=30,
        )
        sampler.start()
        time.sleep(1.5)
        sampler.stop()
        time.sleep(0.2)
        results = [result for state, result in events if state == "READY" and result]
        self.assertEqual(len(results), 1)
        self.assertEqual(
            [c.get("name") for c in results[0]["heroes"]["candidates"]],
            ["森林游侠", "神秘法师", "魔镜"],
        )


if __name__ == "__main__":
    unittest.main()
