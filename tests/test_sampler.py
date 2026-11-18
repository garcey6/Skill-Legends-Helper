"""Live sampler stability tests."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.kb.recommend import Advisor
from app.live.frame import Frame, SourceState
from app.live.replaysrc import ImageFrameSource
from app.live.sampler import LiveSampler, consistent_frames
from app.vision.glyphs import GlyphMatcher
from app.vision.schools import SchoolMatcher

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))
SCHOOLS = json.loads((ROOT / "data" / "recognize" / "schools_chroma.json").read_text(encoding="utf-8"))
GLYPHS = json.loads((ROOT / "data" / "recognize" / "glyphs.json").read_text(encoding="utf-8"))


class BlankSource:
    """A found game window whose rune strip is temporarily not visible."""

    def __init__(self) -> None:
        self.frame_id = 0

    def state(self) -> SourceState:
        return SourceState(
            found=True,
            foreground=True,
            client_w=1800,
            client_h=1118,
            capture_method="fake",
            state="READY",
            hwnd=1,
        )

    def grab(self, roi):
        self.frame_id += 1
        image = np.zeros((40, 200, 3), dtype=np.uint8)
        return Frame(image=image, frame_id=self.frame_id, timestamp=0.0, roi=roi, source="fake")


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

    def test_watching_keeps_last_accepted_round(self) -> None:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        sampler = LiveSampler(
            BlankSource(),
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: None,
            interval_ms=30,
        )
        sampler._last_fingerprint = "森林游侠"
        sampler._last_icons = np.zeros((40, 200, 3), dtype=np.uint8)
        sampler._last_names = np.zeros((40, 200, 3), dtype=np.uint8)
        sampler.start()
        time.sleep(0.15)
        sampler.stop()
        time.sleep(0.05)
        self.assertEqual(sampler._last_fingerprint, "森林游侠")

    def test_asset_provider_switches_bundle_on_width_change(self) -> None:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        fhd = SimpleNamespace(
            group=SimpleNamespace(id="fhd"),
            school_matcher=matcher,
            glyph_matcher=glyph,
            ocr_matcher=None,
        )
        qhd = SimpleNamespace(
            group=SimpleNamespace(id="qhd"),
            school_matcher=matcher,
            glyph_matcher=glyph,
            ocr_matcher=None,
        )
        widths = []

        def provider(width: int):
            widths.append(width)
            return qhd if width >= 2560 else fhd

        sampler = LiveSampler(
            ImageFrameSource(ROOT / "samples" / "draft_001.png"),
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: None,
            interval_ms=30,
            asset_provider=provider,
        )
        self.assertTrue(sampler._select_assets(1920))
        self.assertIs(sampler._assets, fhd)
        self.assertTrue(sampler._select_assets(2200))
        self.assertIs(sampler._assets, fhd)
        self.assertTrue(sampler._select_assets(2560))
        self.assertIs(sampler._assets, qhd)
        self.assertEqual(widths, [1920, 2200, 2560])

    def test_asset_provider_failure_keeps_previous_bundle(self) -> None:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        good = SimpleNamespace(
            group=SimpleNamespace(id="hd"),
            school_matcher=matcher,
            glyph_matcher=glyph,
            ocr_matcher=None,
        )

        def provider(width: int):
            if width >= 2560:
                raise FileNotFoundError("missing qhd templates")
            return good

        sampler = LiveSampler(
            ImageFrameSource(ROOT / "samples" / "draft_001.png"),
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: None,
            interval_ms=30,
            asset_provider=provider,
        )
        self.assertTrue(sampler._select_assets(1280))
        self.assertFalse(sampler._select_assets(2560))
        self.assertIs(sampler._assets, good)


if __name__ == "__main__":
    unittest.main()
