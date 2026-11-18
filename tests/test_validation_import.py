"""Real-frame holdout importer tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.kb.recommend import Advisor
from tools.import_validation import import_case, normalize_heroes, normalize_schools


class ImportValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "holdout"
        self.dataset.mkdir()
        self.image = self.root / "capture.png"
        Image.new("RGB", (800, 450), (30, 40, 50)).save(self.image)
        self.advisor = Advisor()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_import_case_copies_image_and_writes_meta(self) -> None:
        case = import_case(
            self.image,
            "holdout_001",
            ["渣克鼠王", "神秘法师"],
            None,
            "1920x1080 窗口化",
            self.dataset,
            advisor=self.advisor,
        )

        self.assertEqual(case["client"], "holdout_001.png")
        self.assertEqual(case["expected"]["heroes"], ["渣客鼠王", "神秘法师"])
        self.assertIsNone(case["expected"]["schools"])
        self.assertEqual(case["resolution"], [800, 450])
        self.assertTrue((self.dataset / "holdout_001.png").is_file())
        meta = json.loads((self.dataset / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["cases"]), 1)
        self.assertEqual(meta["cases"][0]["name"], "holdout_001")
        self.assertIn("真实", meta["description"])

    def test_duplicate_name_is_rejected_without_touching_existing_case(self) -> None:
        import_case(self.image, "holdout_001", ["神秘法师"], None, "", self.dataset, advisor=self.advisor)
        original = (self.dataset / "holdout_001.png").read_bytes()

        with self.assertRaises(ValueError):
            import_case(self.image, "holdout_001", ["魔镜"], None, "", self.dataset, advisor=self.advisor)

        meta = json.loads((self.dataset / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["cases"]), 1)
        self.assertEqual(meta["cases"][0]["expected"]["heroes"], ["神秘法师"])
        self.assertEqual((self.dataset / "holdout_001.png").read_bytes(), original)

    def test_unknown_hero_and_school_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知英雄"):
            import_case(self.image, "holdout_001", ["不存在的英雄"], None, "", self.dataset, advisor=self.advisor)
        with self.assertRaisesRegex(ValueError, "未知流派"):
            import_case(
                self.image,
                "holdout_001",
                ["神秘法师"],
                ["不存在的流派"],
                "",
                self.dataset,
                advisor=self.advisor,
            )
        self.assertFalse((self.dataset / "holdout_001.png").exists())
        self.assertFalse((self.dataset / "meta.json").exists())

    def test_replace_updates_heroes_and_keeps_one_case(self) -> None:
        import_case(self.image, "holdout_001", ["神秘法师"], None, "", self.dataset, advisor=self.advisor)
        case = import_case(
            self.image,
            "holdout_001",
            ["魔镜"],
            ["普攻流"],
            "修正标注",
            self.dataset,
            replace=True,
            advisor=self.advisor,
        )
        self.assertEqual(case["expected"]["heroes"], ["魔镜"])
        self.assertEqual(case["expected"]["schools"], ["普攻流"])
        meta = json.loads((self.dataset / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["cases"]), 1)
        self.assertEqual(meta["cases"][0]["note"], "修正标注")

    def test_tiny_image_is_rejected(self) -> None:
        tiny = self.root / "tiny.png"
        Image.new("RGB", (100, 80), (0, 0, 0)).save(tiny)
        with self.assertRaisesRegex(ValueError, "分辨率"):
            import_case(tiny, "tiny", ["神秘法师"], None, "", self.dataset, advisor=self.advisor)

    def test_rgba_is_converted_to_rgb(self) -> None:
        rgba = self.root / "rgba.png"
        Image.new("RGBA", (800, 450), (1, 2, 3, 128)).save(rgba)
        import_case(rgba, "rgba", ["神秘法师"], None, "", self.dataset, advisor=self.advisor)
        with Image.open(self.dataset / "rgba.png") as image:
            self.assertEqual(image.mode, "RGB")


class NormalizeNamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.advisor = Advisor()

    def test_aliases_map_to_canonical_names(self) -> None:
        self.assertEqual(
            normalize_heroes(["渣克鼠王", "神秘法师"], self.advisor),
            ["渣客鼠王", "神秘法师"],
        )

    def test_duplicate_hero_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "重复"):
            normalize_heroes(["神秘法师", "神秘法师"], self.advisor)

    def test_schools_accept_names_and_ids(self) -> None:
        self.assertEqual(
            normalize_schools(["普攻流", "ultimate"], self.advisor),
            ["普攻流", "大招流"],
        )


if __name__ == "__main__":
    unittest.main()
