"""Regression tests for HUD state transitions during live recognition."""
from __future__ import annotations

import time
import unittest
from unittest import mock

from PIL import Image

import agent as agent_module
from agent import Agent

ENABLED = ["普攻流", "回复流", "大招流", "中毒流", "护盾流", "精灵流", "怒气流", "急速流"]
BANNED = ["闪避流", "暴击流", "生命流", "冰冻流", "易伤流"]


class FakeHud:
    def __init__(self) -> None:
        self.visible = True
        self.ready_calls = 0
        self.shown = []
        self.last_image = Image.new("RGB", (620, 500))
        self.last_position = (1920, 900)

    def screen_rect(self):
        if not self.visible:
            return None
        x, y = self.last_position
        return (x, y, x + self.last_image.width, y + self.last_image.height)

    def show_ready(self, _url: str) -> None:
        self.ready_calls += 1
        self.visible = True

    def show(self, image, _hwnd=None) -> None:
        self.shown.append(image)
        self.visible = True


class FakeAdvisor:
    def recommend(self, heroes, enabled, banned):
        return {"recommendations": [{"name": heroes[0], "score": 1.0}]}


def _make_agent() -> Agent:
    agent = Agent.__new__(Agent)
    agent.hud = FakeHud()
    agent._live_has_result = True
    agent._live_ready_since = None
    agent.server_url = "http://127.0.0.1:8777"
    agent.advisor = FakeAdvisor()
    agent.live_source = None
    agent.last_game_hwnd = 0
    agent.capture_key = "F8"
    agent.toggle_key = "F9"
    agent.quit_key = "Ctrl+Alt+Q"
    agent.live_school_by_name = {name: name for name in ENABLED + BANNED}
    return agent


def _ready_payload():
    return {
        "schools": {"status": "ok", "enabled": ENABLED, "banned": BANNED},
        "heroes": {"candidates": [{"name": "森林游侠"}]},
    }


class LiveHudStateTest(unittest.TestCase):
    def test_transient_watching_keeps_the_result_card(self) -> None:
        agent = _make_agent()
        with mock.patch.object(agent_module, "render_result", return_value=Image.new("RGB", (10, 10))):
            agent._handle_live("READY", _ready_payload())
        self.assertEqual(len(agent.hud.shown), 1)
        self.assertTrue(agent._live_has_result)

        # A single unstable probe frame must not replace the analysis with the
        # "ready" card; otherwise the HUD flashes between the two states.
        agent._handle_live("WATCHING", None)
        self.assertEqual(agent.hud.ready_calls, 0)
        self.assertTrue(agent._live_has_result)

    def test_sustained_watching_falls_back_to_ready_once(self) -> None:
        agent = _make_agent()
        agent._live_ready_since = time.monotonic() - agent_module.LIVE_READY_GRACE_SECONDS - 0.1
        agent._handle_live("WATCHING", None)
        self.assertEqual(agent.hud.ready_calls, 1)
        self.assertFalse(agent._live_has_result)
        agent._handle_live("WATCHING", None)
        self.assertEqual(agent.hud.ready_calls, 1)

    def test_idle_falls_back_immediately(self) -> None:
        agent = _make_agent()
        agent._handle_live("IDLE", None)
        self.assertEqual(agent.hud.ready_calls, 1)
        self.assertFalse(agent._live_has_result)

    def test_live_mask_ignores_the_hud_overlap_in_the_icon_roi(self) -> None:
        agent = _make_agent()
        agent.live_source = mock.Mock(hwnd=77)
        with mock.patch.object(agent_module.capture, "client_box", return_value=(0, 0, 2560, 1600)):
            rects = agent._live_mask_rects(2560, 1600, (0.18, 0.88, 0.86, 0.995))
        self.assertEqual(rects, [(1459, 0, 1792, 24)])

        agent.hud.visible = False
        self.assertEqual(agent._live_mask_rects(2560, 1600, (0.18, 0.88, 0.86, 0.995)), [])

    def test_same_draft_restores_the_last_result_after_a_gap(self) -> None:
        agent = _make_agent()
        agent._live_last_image = Image.new("RGB", (10, 10))
        agent._live_has_result = False
        agent._handle_live("READY", None)
        self.assertEqual(len(agent.hud.shown), 1)
        self.assertTrue(agent._live_has_result)


if __name__ == "__main__":
    unittest.main()
