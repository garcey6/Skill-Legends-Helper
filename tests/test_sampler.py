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
from app.live.stability import diff_ratio_masked, roi_overlap_rects
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


class HudOverlaySource(ImageFrameSource):
    """The real draft plus a HUD-shaped patch while the overlay is visible."""

    def __init__(self, path, icons_roi) -> None:
        super().__init__(path)
        self.icons_roi = tuple(icons_roi)
        self.hud_visible = True
        self.capture_count = 0

    def grab(self, roi):
        frame = super().grab(roi)
        if frame is not None and tuple(roi) == self.icons_roi and self.hud_visible:
            image = frame.image.copy()
            height, width = image.shape[:2]
            patch = min(160, max(1, width // 5))
            image[0:25, width - patch:width] = (20, 28, 38)
            frame = Frame(image, frame.frame_id, frame.timestamp, frame.roi, frame.source)
        return frame


class HudMaskTest(unittest.TestCase):
    def _sampler(self, mask_provider=None) -> LiveSampler:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        return LiveSampler(
            ImageFrameSource(ROOT / "samples" / "draft_001.png"),
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: None,
            interval_ms=30,
            mask_provider=mask_provider,
        )

    def test_masked_diff_ignores_the_overlay_only(self) -> None:
        clean = np.zeros((20, 40, 3), dtype=np.uint8)
        dirty = clean.copy()
        dirty[0:10, 10:20] = 255
        self.assertGreater(diff_ratio_masked(dirty, clean), 0.0)
        self.assertEqual(diff_ratio_masked(dirty, clean, [(10, 0, 20, 10)]), 0.0)

    def test_roi_overlap_uses_client_origin_and_roi(self) -> None:
        # 100x50 client at screen (1000, 200); icon ROI is the bottom strip.
        rects = roi_overlap_rects(
            (0.2, 0.8, 0.6, 1.0),
            (100, 50),
            (1000, 200),
            (1010, 225, 1060, 260),
        )
        self.assertEqual(rects, [(0, 0, 40, 20)])

    def test_sampler_does_not_recapture_when_only_the_hud_changed(self) -> None:
        advisor = Advisor()
        matcher = SchoolMatcher(SCHOOLS, float(LAYOUT.get("margin_min", 0.012)))
        glyph = GlyphMatcher(GLYPHS, [h["name"] for h in advisor.heroes])
        icons_roi = tuple(LAYOUT["rois"]["icons"])
        source = HudOverlaySource(ROOT / "samples" / "draft_001.png", icons_roi)

        def before_capture() -> None:
            source.capture_count += 1
            source.hud_visible = False

        def after_capture() -> None:
            source.hud_visible = True

        def mask_provider(client_w: int, client_h: int, roi: tuple):
            del client_h, roi
            width = int(round((icons_roi[1] - icons_roi[0]) * client_w))
            patch = min(160, max(1, width // 5))
            return [(width - patch, 0, width, 25)]

        sampler = LiveSampler(
            source,
            LAYOUT,
            matcher,
            glyph,
            lambda state, result: None,
            interval_ms=30,
            before_capture=before_capture,
            after_capture=after_capture,
            mask_provider=mask_provider,
        )
        sampler.start()
        time.sleep(1.5)
        sampler.stop()
        time.sleep(0.1)
        self.assertEqual(source.capture_count, 1)

    def test_repeated_capture_is_suppressed_when_hud_overlaps(self) -> None:
        clean = np.zeros((40, 200, 3), dtype=np.uint8)
        dirty = clean.copy()
        # The HUD occupies this patch while probing; it is not a draft change.
        dirty[0:20, 150:200] = (20, 28, 38)
        sampler = self._sampler(
            mask_provider=lambda client_w, client_h, roi: roi_overlap_rects(
                roi,
                (client_w, client_h),
                (0, 0),
                (150, 0, 200, 20),
            )
        )
        sampler._last_icons = clean
        sampler._last_names = clean
        self.assertTrue(sampler._probe_is_same(dirty, 200, 40, (0.0, 1.0, 0.0, 1.0)))
        unmasked = self._sampler()
        unmasked._last_icons = clean
        unmasked._last_names = clean
        self.assertFalse(unmasked._probe_is_same(dirty, 200, 40, (0.0, 1.0, 0.0, 1.0)))


if __name__ == "__main__":
    unittest.main()
