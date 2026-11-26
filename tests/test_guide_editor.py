"""Direct-start HUD and guide-editor deep-link regression tests."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import agent
from app.config import guide_editor_url

ROOT = Path(__file__).resolve().parent.parent


class GuideEditorUrlTest(unittest.TestCase):
    def test_url_targets_the_guide_modal(self) -> None:
        self.assertEqual(
            guide_editor_url("http://127.0.0.1:8777/"),
            "http://127.0.0.1:8777/?open=guides",
        )

    def test_agent_opens_the_guide_editor_after_server_starts(self) -> None:
        instance = agent.Agent.__new__(agent.Agent)
        instance.httpd = object()
        instance.server_url = "http://127.0.0.1:8777"
        with mock.patch.object(agent.webbrowser, "open") as open_url:
            instance.open_guide_editor()
        open_url.assert_called_once_with("http://127.0.0.1:8777/?open=guides")

    def test_agent_does_not_open_a_missing_server(self) -> None:
        instance = agent.Agent.__new__(agent.Agent)
        instance.httpd = None
        instance.server_url = ""
        with mock.patch.object(agent.webbrowser, "open") as open_url:
            instance.open_guide_editor()
        open_url.assert_not_called()


class GuideEditorWiringTest(unittest.TestCase):
    def test_hud_has_a_settings_button(self) -> None:
        text = (ROOT / "app" / "overlay" / "hud.py").read_text(encoding="utf-8")
        self.assertIn("settings_command", text)
        self.assertIn("settings_button", text)
        self.assertIn("设置 / 攻略库", text)

    def test_agent_passes_the_button_callback(self) -> None:
        text = (ROOT / "agent.py").read_text(encoding="utf-8")
        self.assertIn("settings_command=self.open_guide_editor", text)
        self.assertIn("guide_editor_url(self.server_url)", text)

    def test_web_console_honors_the_open_guides_query(self) -> None:
        text = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('params.get("open") === "guides"', text)
        self.assertIn("await openGuides()", text)


if __name__ == "__main__":
    unittest.main()
