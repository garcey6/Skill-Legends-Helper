"""Multi-hero HUD rendering regression tests."""
from __future__ import annotations

import unittest

from app.overlay.hud import FOOTER_H, HEADER_H, SCHOOLS_H, render_result


def _card(index: int):
    return {
        "name": "英雄%d" % (index + 1),
        "score": 90 - index,
        "tier": "S",
        "role": "法师",
        "reasons": ["开放流派契合", "核心卡可叠加"],
        "core_cards": [{"name": "先发制人", "rarity": 3, "desc": "开局加攻"}],
        "build": {"schools": ["大招流", "精灵流"], "steps": ["前 3 回合补生存"]},
        "has_guide": True,
        "talent_icon": "",
        "ultimate_icon": "",
    }


def _render(count: int):
    result = {
        "recommendations": [_card(i) for i in range(count)],
        "draft": {"enabled": [], "banned": []},
    }
    return render_result(result)


class HudMultiHeroTest(unittest.TestCase):
    def test_width_stays_fixed(self) -> None:
        self.assertEqual(_render(1).width, 620)

    def test_height_grows_with_hero_count(self) -> None:
        one = _render(1)
        three = _render(3)
        five = _render(5)
        self.assertGreater(three.height, one.height)
        self.assertGreater(five.height, three.height)
        self.assertGreater(five.height, 1100)

    def test_single_hero_uses_a_full_card_not_a_compact_row(self) -> None:
        expected = HEADER_H + SCHOOLS_H + FOOTER_H + 300
        self.assertGreaterEqual(_render(1).height, expected)

    def test_five_heroes_do_not_raise(self) -> None:
        image = _render(5)
        self.assertGreater(image.height, 0)


if __name__ == "__main__":
    unittest.main()
