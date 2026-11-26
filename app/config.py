"""Global paths and small JSON helpers for the 选技助手 app."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
GUIDE_DIR = DATA_DIR / "guides"
TEMPLATE_DIR = DATA_DIR / "templates"
HERO_TEMPLATE_DIR = TEMPLATE_DIR / "heroes"
SCHOOL_TEMPLATE_DIR = TEMPLATE_DIR / "schools"
ART_DIR = DATA_DIR / "art"
STATIC_DIR = BASE_DIR / "static"
SAMPLES_DIR = BASE_DIR / "samples"
UPLOAD_DIR = DATA_DIR / "uploads"
SETTINGS_PATH = DATA_DIR / "settings.json"
SCHOOLS_PATH = DATA_DIR / "schools.json"
HEROES_PATH = DATA_DIR / "heroes.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "llm": {
        "enabled": False,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
        "timeout": 45,
    },
    "recognizer": {
        "reference_width": 1800,
    },
}


def guide_editor_url(base_url: str) -> str:
    """Deep-link the local console to its hero-guide editor modal."""
    return str(base_url).rstrip("/") + "/?open=guides"


def load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def get_settings() -> Dict[str, Any]:
    data = load_json(SETTINGS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    merged = json.loads(json.dumps(DEFAULT_SETTINGS, ensure_ascii=False))
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    current = get_settings()
    if isinstance(data.get("llm"), dict):
        current["llm"].update(data["llm"])
    if isinstance(data.get("recognizer"), dict):
        current["recognizer"].update(data["recognizer"])
    save_json(SETTINGS_PATH, current)
    return current
