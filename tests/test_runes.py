from __future__ import annotations

import unittest

import numpy as np

from app.vision.runes import _fallback_component


class RuneFallbackTest(unittest.TestCase):
    def test_fallback_prefers_central_component_over_page_edge(self) -> None:
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[0, :] = 1
        mask[8:12, 8:12] = 1

        component = _fallback_component(mask)

        self.assertIsNotNone(component)
        assert component is not None
        self.assertEqual(int(component.sum()), 16)
        self.assertEqual(int(component[0].sum()), 0)

    def test_fallback_returns_none_for_tiny_noise(self) -> None:
        mask = np.zeros((10, 10), dtype=np.uint8)
        mask[5, 5] = 1
        self.assertIsNone(_fallback_component(mask))


if __name__ == "__main__":
    unittest.main()
