"""Tall multi-hero HUD viewport tests."""
from __future__ import annotations

import unittest

from PIL import Image

from app.overlay.hud import viewport_crop


class HudScrollTest(unittest.TestCase):
    def test_viewport_crop_clamps(self) -> None:
        image = Image.new("RGB", (100, 1000), "black")
        view, offset = viewport_crop(image, 0, 300)
        self.assertEqual(view.height, 300)
        self.assertEqual(offset, 0)

        view, offset = viewport_crop(image, 900, 300)
        self.assertEqual(view.height, 300)
        self.assertEqual(offset, 700)

        view, offset = viewport_crop(image, -50, 300)
        self.assertEqual(view.height, 300)
        self.assertEqual(offset, 0)

    def test_short_image_is_not_cropped(self) -> None:
        image = Image.new("RGB", (100, 200), "black")
        view, offset = viewport_crop(image, 50, 300)
        self.assertEqual(view.height, 200)
        self.assertEqual(offset, 0)


if __name__ == "__main__":
    unittest.main()
