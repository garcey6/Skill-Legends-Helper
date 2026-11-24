from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.vision.annotation import (
    Annotation,
    AnnotationError,
    Feature,
    parse_annotation,
    update_expected_annotation,
)
from tools.annotate_fixture import AnnotationEditor


class AnnotationModelTest(unittest.TestCase):
    def test_normalized_feature_scales_to_each_client_resolution(self):
        feature = Feature("nameplates", (0.02, 0.35, 0.96, 0.27))

        self.assertEqual(feature.to_pixels(1800, 1118), (36, 391, 1728, 302))
        self.assertEqual(feature.to_pixels(2560, 1600), (51, 560, 2458, 432))

    def test_round_trip_from_pixel_rects_keeps_normalized_coordinates(self):
        annotation = Annotation.from_rects(
            (1800, 1118),
            {
                "icons": (324, 984, 1224, 128),
                "nameplates": (36, 391, 1728, 302),
            },
        )

        self.assertEqual(annotation.features[0].name, "icons")
        self.assertAlmostEqual(annotation.features[0].box[0], 0.18)
        self.assertAlmostEqual(annotation.features[0].box[3], 128 / 1118)
        self.assertEqual(annotation.features[0].to_pixels(2560, 1600), (461, 1408, 1741, 183))

    def test_parse_annotation_accepts_optional_payload(self):
        payload = {
            "base_resolution": {"width": 1800, "height": 1118},
            "features": [
                {"name": "icons", "box": [0.18, 0.88, 0.68, 0.115]},
                {"name": "nameplates", "box": [0.02, 0.35, 0.96, 0.27]},
            ],
        }

        annotation = parse_annotation(payload)

        self.assertIsNotNone(annotation)
        assert annotation is not None
        self.assertEqual(annotation.base_resolution, (1800, 1118))
        self.assertEqual([f.name for f in annotation.features], ["icons", "nameplates"])

    def test_parse_annotation_returns_none_when_absent(self):
        self.assertIsNone(parse_annotation(None))

    def test_parse_annotation_rejects_invalid_boxes_and_duplicate_names(self):
        bad_box = {
            "base_resolution": {"width": 100, "height": 100},
            "features": [{"name": "icons", "box": [0.5, 0.5, 0.6, 0.1]}],
        }
        duplicate = {
            "base_resolution": {"width": 100, "height": 100},
            "features": [
                {"name": "icons", "box": [0.0, 0.0, 0.5, 0.5]},
                {"name": "icons", "box": [0.5, 0.0, 0.5, 0.5]},
            ],
        }

        with self.assertRaises(AnnotationError):
            parse_annotation(bad_box)
        with self.assertRaises(AnnotationError):
            parse_annotation(duplicate)

    def test_update_expected_preserves_labels_and_adds_annotation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(
                json.dumps({"heroes": ["甲", "乙"], "schools": None}, ensure_ascii=False),
                encoding="utf-8",
            )
            annotation = Annotation.from_rects(
                (1800, 1118), {"icons": (324, 984, 1224, 128)}
            )

            payload = update_expected_annotation(path, annotation)

            self.assertEqual(payload["heroes"], ["甲", "乙"])
            self.assertEqual(payload["annotation"]["base_resolution"], {"width": 1800, "height": 1118})
            self.assertEqual(payload["annotation"]["features"][0]["name"], "icons")


class AnnotationEditorTest(unittest.TestCase):
    def test_editor_adds_and_replaces_rects_and_scales_to_another_resolution(self):
        editor = AnnotationEditor((1800, 1118))
        editor.add_rect("icons", (324, 984, 1224, 128))

        self.assertEqual(editor.annotation().to_pixels(1800, 1118)["icons"], (324, 984, 1224, 128))
        self.assertEqual(editor.rects["icons"], (324, 984, 1224, 128))

        editor.rects.clear()
        editor.add_rect("nameplates", (36, 391, 1728, 302))
        self.assertEqual(editor.annotation().to_pixels(2560, 1600)["nameplates"], (51, 560, 2458, 432))

    def test_editor_rejects_duplicate_names_and_out_of_bounds_rects(self):
        editor = AnnotationEditor((100, 100))
        editor.add_rect("icons", (0, 0, 50, 50))

        with self.assertRaises(ValueError):
            editor.add_rect("icons", (50, 50, 10, 10))
        with self.assertRaises(ValueError):
            editor.add_rect("outside", (90, 90, 20, 20))
        self.assertEqual(editor.rects, {"icons": (0, 0, 50, 50)})


class AnnotationFixtureTest(unittest.TestCase):
    def test_existing_fixtures_can_carry_cross_resolution_annotations(self):
        root = Path(__file__).resolve().parent / "fixtures" / "expected"
        draft = json.loads((root / "draft001_1800x1118.json").read_text(encoding="utf-8"))
        wide = json.loads((root / "screenshot_2560_30.json").read_text(encoding="utf-8"))

        draft_annotation = parse_annotation(draft.get("annotation"))
        wide_annotation = parse_annotation(wide.get("annotation"))

        self.assertIsNotNone(draft_annotation)
        self.assertIsNotNone(wide_annotation)
        assert draft_annotation is not None and wide_annotation is not None
        self.assertEqual(
            [f.name for f in draft_annotation.features],
            [f.name for f in wide_annotation.features],
        )
        self.assertNotEqual(draft_annotation.base_resolution, wide_annotation.base_resolution)
