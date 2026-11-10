import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from app.kb.recommend import Advisor
from app.overlay import hud
from app.overlay.hotkey import parse_combo, parse_key
from app.vision.recognizer import Recognizer

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "draft_001.png"


class OverlayRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recognizer = Recognizer()
        result = recognizer.analyze(Image.open(SAMPLE))
        heroes = [h["name"] for h in result["heroes"]]
        enabled = [s["id"] for s in result["schools"]["enabled"]]
        banned = [s["id"] for s in result["schools"]["banned"]]
        cls.recommendation = Advisor().recommend(heroes, enabled, banned)

    def test_result_render(self):
        self.assertTrue(self.recommendation["recommendations"][0]["core_cards"])
        image = hud.render_result(self.recommendation)
        self.assertEqual(image.size, (hud.WIDTH, hud.HEIGHT))
        array = np.asarray(image.convert("RGB"))
        self.assertGreater(int(array.max()), 150)
        self.assertGreater(float(array.std()), 10.0)

    def test_states_render(self):
        self.assertEqual(hud.render_ready("http://127.0.0.1:8777").size, (hud.WIDTH, 160))
        self.assertEqual(hud.render_loading().size, (hud.WIDTH, 168))
        self.assertEqual(hud.render_error("黑屏", "请使用无边框窗口").size, (hud.WIDTH, 250))


class HotkeyParseTest(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(parse_key("F8"), 0x77)
        self.assertEqual(parse_key("f9"), 0x78)
        self.assertEqual(parse_key("Q"), ord("Q"))

    def test_combo(self):
        mods, vk = parse_combo("Ctrl+Alt+Q")
        self.assertEqual(mods, 3)
        self.assertEqual(vk, ord("Q"))
        self.assertEqual(parse_combo("F8"), (0, 0x77))
        self.assertEqual(parse_combo("Alt+C"), (1, ord("C")))
        self.assertEqual(parse_combo("Alt+X"), (1, ord("X")))


if __name__ == "__main__":
    unittest.main()
