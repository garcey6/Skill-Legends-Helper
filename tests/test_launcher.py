"""Single launcher and one-hero warning regression tests."""
from __future__ import annotations

import unittest
from pathlib import Path

import agent

ROOT = Path(__file__).resolve().parent.parent


class LauncherTest(unittest.TestCase):
    def test_only_one_launcher(self) -> None:
        self.assertTrue((ROOT / "启动助手.bat").exists())
        self.assertFalse((ROOT / "启动浮窗.bat").exists())
        self.assertFalse((ROOT / "启动网页版.bat").exists())
        self.assertFalse((ROOT / "打开设置.bat").exists())

    def test_launcher_starts_overlay_directly(self) -> None:
        text = (ROOT / "启动助手.bat").read_text(encoding="utf-8")
        self.assertIn("agent.py --port 8777", text)
        self.assertNotIn("run.py", text)
        self.assertNotIn("choice", text)
        self.assertNotIn(":menu", text)

    def test_hero_warning_for_one_hero(self) -> None:
        self.assertEqual(agent.hero_warning([{"name": "森林游侠"}]), "")
        self.assertIn("1", agent.hero_warning([{"name": None}]))


if __name__ == "__main__":
    unittest.main()
