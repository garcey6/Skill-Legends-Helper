"""Resolution-group selection and cached template loading."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.vision.assets import (
    AssetCache,
    TemplateGroup,
    missing_template_files,
    select_template_group,
)

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))


class TemplateGroupSelectionTest(unittest.TestCase):
    def test_reference_resolution_is_recorded(self) -> None:
        self.assertEqual(LAYOUT["reference_resolution"]["width"], 1800)
        self.assertEqual(LAYOUT["reference_resolution"]["height"], 1118)

    def test_widths_select_expected_group(self) -> None:
        cases = [
            (1280, "hd"),
            (1919, "hd"),
            (1920, "fhd"),
            (2559, "fhd"),
            (2560, "qhd"),
            (3840, "qhd"),
        ]
        for width, expected in cases:
            with self.subTest(width=width):
                self.assertEqual(select_template_group(LAYOUT, width).id, expected)

    def test_zero_width_falls_back_to_reference(self) -> None:
        group = select_template_group(LAYOUT, 0)
        self.assertEqual(group.id, "hd")

    def test_groups_cover_every_width_once(self) -> None:
        groups = [TemplateGroup.from_dict(item) for item in LAYOUT["template_groups"]]
        for width in range(1, 4001):
            hits = [group for group in groups if group.contains(width)]
            self.assertEqual(len(hits), 1, width)

    def test_group_files_exist(self) -> None:
        self.assertEqual(
            missing_template_files(LAYOUT, ROOT / "data" / "recognize"),
            [],
        )

    def test_missing_group_files_are_reported_with_full_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = missing_template_files(LAYOUT, Path(tmp))
            self.assertEqual(len(missing), 9)
            self.assertTrue(all(item.startswith(tmp) for item in missing))

    def test_legacy_layout_without_groups_still_loads(self) -> None:
        group = select_template_group({"reference_width": 1800}, 1920)
        self.assertEqual(group.id, "default")
        self.assertTrue(group.contains(1920))

    def test_uncovered_width_is_an_error_not_a_silent_default(self) -> None:
        layout = {
            "reference_resolution": {"width": 1800},
            "template_groups": [
                {
                    "id": "hd",
                    "min_width": 0,
                    "max_width": 1919,
                    "reference_width": 1800,
                    "schools": "schools_chroma.json",
                    "runes": "school_runes.json",
                    "glyphs": "glyphs.json",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "1920"):
            select_template_group(layout, 1920)


class AssetCacheTest(unittest.TestCase):
    def test_cache_reuses_bundle_for_same_group(self) -> None:
        cache = AssetCache(
            LAYOUT,
            ROOT / "data" / "recognize",
            ["神秘法师"],
            use_ocr=False,
        )
        first = cache.for_width(1920)
        second = cache.for_width(2000)
        self.assertIs(first, second)
        self.assertEqual(first.group.id, "fhd")
        self.assertEqual(cache.for_width(2560).group.id, "qhd")
        self.assertIsNone(first.ocr_matcher)

    def test_live_recognize_reports_selected_group(self) -> None:
        from tools.live_recognize import load_assets

        assets = load_assets(use_ocr=False, width=2560)
        self.assertEqual(assets["template_group"]["id"], "qhd")

    def test_live_agent_uses_the_resolution_aware_cache(self) -> None:
        # Guard the runtime wiring itself: layout metadata and AssetCache are
        # only useful if the live agent selects a bundle for the client width.
        source = (ROOT / "agent.py").read_text(encoding="utf-8")
        self.assertIn("AssetCache(", source)
        self.assertIn("asset_provider=self._live_assets_for_width", source)
        self.assertIn(".for_width(client_width)", source)

    def test_groups_have_independent_matchers_and_own_reference_width(self) -> None:
        cache = AssetCache(
            LAYOUT,
            ROOT / "data" / "recognize",
            ["神秘法师"],
            use_ocr=False,
        )
        hd = cache.for_width(1280)
        qhd = cache.for_width(2560)
        self.assertIsNot(hd.school_matcher, qhd.school_matcher)
        self.assertIsNot(hd.glyph_matcher, qhd.glyph_matcher)
        self.assertNotEqual(hd.group.id, qhd.group.id)
        self.assertNotEqual(hd.group.reference_width, qhd.group.reference_width)
        self.assertEqual(hd.group.reference_width, 1800)
        self.assertEqual(qhd.group.reference_width, 2560)


if __name__ == "__main__":
    unittest.main()
