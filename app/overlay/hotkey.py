"""Global hotkeys for the floating HUD (Win32 RegisterHotKey, no dependencies)."""
from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes
from typing import Dict, List, Optional, Tuple

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
KEYEVENTF_KEYUP = 0x0002


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def parse_key(name: str) -> int:
    text = (name or "").strip().upper()
    if not text:
        raise ValueError("空按键")
    if text.startswith("F") and text[1:].isdigit():
        number = int(text[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    aliases = {
        "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B, "ESCAPE": 0x1B,
        "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
        "PAGEUP": 0x21, "PAGEDOWN": 0x22, "UP": 0x26, "DOWN": 0x28,
        "LEFT": 0x25, "RIGHT": 0x27,
    }
    if text in aliases:
        return aliases[text]
    if len(text) == 1 and (text.isalnum()):
        return ord(text)
    raise ValueError("无法识别按键：%s" % name)


def parse_combo(name: str) -> Tuple[int, int]:
    parts = [part.strip() for part in (name or "").split("+") if part.strip()]
    if not parts:
        raise ValueError("空快捷键")
    mods = 0
    for part in parts[:-1]:
        upper = part.upper()
        if upper in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif upper == "ALT":
            mods |= MOD_ALT
        elif upper == "SHIFT":
            mods |= MOD_SHIFT
        elif upper in ("WIN", "WINDOWS"):
            mods |= MOD_WIN
        else:
            raise ValueError("未知修饰键：%s" % part)
    return mods, parse_key(parts[-1])


class HotkeyManager:
    """Register global hotkeys (capture/toggle/quit, optional debug)."""

    def __init__(
        self,
        events: "queue.Queue[str]",
        capture: str = "F8",
        toggle: str = "F9",
        quit_combo: str = "Ctrl+Alt+Q",
        debug: Optional[str] = None,
    ) -> None:
        self.events = events
        self.bindings: Dict[int, Tuple[int, int, str]] = {}
        self.errors: List[str] = []
        bindings = [(capture, "capture"), (toggle, "toggle"), (quit_combo, "quit")]
        if debug:
            bindings.append((debug, "debug"))
        for ident, (combo, action) in enumerate(bindings, start=1):
            try:
                mods, vk = parse_combo(combo)
                self.bindings[ident] = (mods, vk, action)
            except ValueError as exc:
                self.errors.append(str(exc))
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._ready = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(1.5)

    def _loop(self) -> None:
        self._thread_id = int(kernel32.GetCurrentThreadId())
        for ident, (mods, vk, _action) in self.bindings.items():
            if not user32.RegisterHotKey(None, ident, mods | MOD_NOREPEAT, vk):
                code = ctypes.get_last_error()
                self.errors.append("热键注册失败（id=%d, vk=0x%X, code=%d）" % (ident, vk, code))
        # Force creation of this thread's message queue even if all hotkeys failed.
        msg = MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self._ready.set()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == WM_HOTKEY:
                binding = self.bindings.get(int(msg.wParam))
                if binding:
                    self.events.put(binding[2])
        for ident in self.bindings:
            user32.UnregisterHotKey(None, ident)

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
