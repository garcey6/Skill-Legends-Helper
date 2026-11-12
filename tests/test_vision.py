import unittest
from pathlib import Path

from PIL import Image

from app.vision.recognizer import Recognizer

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "draft_001.png"

EXPECTED_ENABLED = {"basic", "ultimate", "shield", "rage", "heal", "poison", "spirit", "haste"}
EXPECTED_BANNED = {"dodge", "crit", "life", "freeze", "vulnerable"}


class RecognizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = Recognizer()

    def test_sample_draft(self):
        result = self.recognizer.analyze(Image.open(SAMPLE))
        self.assertEqual([h["name"] for h in result["heroes"]], ["森林游侠", "神秘法师", "魔镜"])
        self.assertEqual({s["id"] for s in result["schools"]["enabled"]}, EXPECTED_ENABLED)
        self.assertEqual({s["id"] for s in result["schools"]["banned"]}, EXPECTED_BANNED)
        self.assertEqual(len(result["schools"]["enabled"]), 8)
        self.assertEqual(len(result["schools"]["banned"]), 5)
        self.assertEqual(result["warnings"], [])

    def test_scaled_screenshot(self):
        image = Image.open(SAMPLE).resize((1280, 795), Image.LANCZOS)
        result = self.recognizer.analyze(image)
        self.assertEqual([h["name"] for h in result["heroes"]], ["森林游侠", "神秘法师", "魔镜"])
        self.assertEqual({s["id"] for s in result["schools"]["enabled"]}, EXPECTED_ENABLED)
        self.assertEqual({s["id"] for s in result["schools"]["banned"]}, EXPECTED_BANNED)

    def test_debug_geometry(self):
        result = self.recognizer.analyze(Image.open(SAMPLE), debug=True)
        self.assertEqual(result["debug"]["grid_method"], "ban_rings")
        self.assertEqual(len(result["debug"]["slots"]), 13)

    def test_ban_status_matches_grid(self):
        result = self.recognizer.analyze(Image.open(SAMPLE))
        for index, school in enumerate(result["schools"]["enabled"]):
            self.assertFalse(school["banned"])
        for school in result["schools"]["banned"]:
            self.assertTrue(school["banned"])

    def test_diagnostics_for_sample(self):
        result = self.recognizer.analyze(Image.open(SAMPLE))
        diag = result["diagnostics"]
        self.assertTrue(diag["panel_found"])
        self.assertEqual(diag["nameplates"], 5)
        self.assertEqual(diag["matched_heroes"], 3)
        self.assertEqual(diag["schools"], 13)

    def test_missing_panel_does_not_fake_schools(self):
        result = self.recognizer.analyze(Image.new("RGB", (1600, 900), (10, 12, 16)))
        self.assertFalse(result["diagnostics"]["panel_found"])
        self.assertEqual(result["diagnostics"]["schools"], 0)
        self.assertEqual(result["schools"]["enabled"], [])
        self.assertEqual(result["schools"]["banned"], [])
        self.assertTrue(any("未能定位流派面板" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
