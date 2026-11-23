from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image

from app.overlay.debug import fit_debug_image, position_path, render_debug_image, save_debug_png, user_debug_dir
from app.vision.debugframe import build_debug_frame


LAYOUT = {
    "rois": {
        "icons": [0.18, 0.88, 0.86, 0.995],
        "nameplates": [0.02, 0.98, 0.35, 0.62],
    }
}


def _result(status="ok"):
    return {
        "session": {"state": "READY"},
        "schools": {
            "status": status,
            "confidence": "high",
            "enabled": ["普攻流", "大招流"],
            "banned": ["闪避流"],
            "margins": [0.91, 0.83],
            "run_count": 2,
        },
        "heroes": {
            "candidates": [
                {"slot": 0, "name": "森林游侠", "score": 0.97, "source": "ocr", "ocr_text": "森林游侠"},
                {"slot": 1, "name": None, "score": 0.0, "source": "glyph", "ocr_text": ""},
            ],
            "engine": "rapidocr",
        },
        "warnings": ["英雄槽位 2 未识别"] if status == "ok" else ["图标条 run 数 13，预期 8"],
        "timings_ms": {"schools": 12.5, "heroes": 8.0, "total": 21.0},
        "runs": [
            {"x0": 100, "x1": 150, "cx": 125.0, "cy": 300.0, "w": 50},
            {"x0": 200, "x1": 250, "cx": 225.0, "cy": 300.0, "w": 50},
        ],
        "plate_boxes": [(10, 400, 110, 440), (120, 400, 220, 440)],
        "glyph_boxes": [],
    }


def test_build_debug_frame_contains_rois_ocr_templates_and_timing():
    frame = build_debug_frame(_result(), LAYOUT, (1800, 1118))
    assert frame.image_size == (1800, 1118)
    assert [box.label for box in frame.rois] == ["图标条", "英雄名牌"]
    assert frame.rois[0].x == 324
    assert frame.rois[0].y == 961
    assert frame.ocr[0].label == "森林游侠"
    assert frame.ocr[0].score == 0.97
    assert (frame.ocr[0].x, frame.ocr[0].y) == (46, 791)
    assert frame.ocr[1].label == "未识别"
    assert frame.templates[0].label == "普攻流"
    assert frame.templates[0].score == 0.91
    assert (frame.templates[0].x, frame.templates[0].y) == (424, 1236)
    assert frame.timings_ms["total"] == 21.0
    assert "未识别" in frame.failure_reason
    assert json.loads(json.dumps(frame.to_dict(), ensure_ascii=False))["ocr"][0]["label"] == "森林游侠"


def test_failed_schools_are_visible_in_failure_reason():
    frame = build_debug_frame(_result("failed"), LAYOUT, (1800, 1118))
    assert "流派识别 failed" in frame.failure_reason
    assert frame.templates[0].label == "未标注"


def test_render_debug_image_preserves_size_and_draws():
    source = Image.new("RGB", (400, 300), (20, 28, 38))
    frame = build_debug_frame(_result(), LAYOUT, (1800, 1118))
    rendered = render_debug_image(source, frame, layers=("roi", "ocr", "templates"))
    assert rendered.size == source.size
    assert rendered.tobytes() != source.tobytes()


def test_large_screenshot_fits_overlay_but_png_keeps_original_size(tmp_path):
    source = Image.new("RGB", (2560, 1390), (20, 28, 38))
    frame = build_debug_frame(_result(), LAYOUT, source.size)
    display = fit_debug_image(source, 1728, 918)
    assert display.size == (1690, 918)
    path = save_debug_png(source, frame, out_dir=tmp_path / "out")
    with Image.open(path) as saved:
        assert saved.size == source.size


def test_debug_files_live_under_user_appdata_not_data(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert user_debug_dir() == tmp_path / "Roaming" / "SkillLegendsHelper"
    assert position_path() == user_debug_dir() / "debug_overlay.json"
    assert "data" not in str(position_path())
    source = Image.new("RGB", (400, 300), (20, 28, 38))
    frame = build_debug_frame(_result(), LAYOUT, (1800, 1118))
    path = save_debug_png(source, frame, out_dir=tmp_path / "out")
    assert path.exists()
    assert path.parent == tmp_path / "out"


def test_debug_overlay_close_notifies_once():
    from app.overlay import debug as debug_module

    calls = []
    overlay = debug_module.DebugOverlay.__new__(debug_module.DebugOverlay)
    overlay._closed = False
    overlay.visible = True
    overlay.top = type("Top", (), {"destroy": lambda self: None})()
    overlay.on_close = lambda: calls.append("closed")
    overlay.close()
    overlay.close()
    assert overlay.visible is False
    assert calls == ["closed"]
