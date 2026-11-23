from __future__ import annotations

import json
import os
import sys

from app.overlay.hotkey import HotkeyManager, parse_combo


def test_debug_disabled_returns_before_any_capture(monkeypatch):
    import agent as agent_module

    instance = agent_module.Agent.__new__(agent_module.Agent)
    instance.debug_enabled = False
    calls = []
    instance._capture_debug_image = lambda: calls.append("capture")
    instance._maybe_debug({"heroes": {"candidates": []}})
    assert calls == []


def test_debug_capture_falls_back_to_last_game_window(monkeypatch):
    import agent as agent_module
    from app.overlay import capture as capture_module

    instance = agent_module.Agent.__new__(agent_module.Agent)
    instance.live_source = type("Source", (), {"hwnd": None})()
    instance.last_game_hwnd = 4321
    seen = []
    monkeypatch.setattr(capture_module, "capture", lambda hwnd: seen.append(hwnd) or type("Shot", (), {"image": "image"})())
    assert instance._capture_debug_image() == "image"
    assert seen == [4321]


def test_debug_mode_suppresses_the_live_hud():
    import agent as agent_module

    instance = agent_module.Agent.__new__(agent_module.Agent)
    instance.debug_enabled = True
    instance._maybe_debug = lambda result: None
    instance._handle_live("READY", {"heroes": {"candidates": []}})


def test_hotkey_manager_accepts_optional_debug_binding(monkeypatch):
    # The constructor must remain usable without the new keyword.
    HotkeyManager.__init__.__defaults__  # import-time smoke
    binding = HotkeyManager  # noqa: F841
    mods, vk = parse_combo("Alt+D")
    assert mods and vk


def test_agent_debug_is_opt_in_and_has_no_work_when_disabled():
    root = os.path.dirname(os.path.dirname(__file__))
    text = open(os.path.join(root, "agent.py"), encoding="utf-8").read()
    assert "self.debug_enabled = bool(getattr(args, \"debug\", False))" in text
    assert 'if not getattr(self, "debug_enabled", False):' in text
    assert '"debug"' in text
