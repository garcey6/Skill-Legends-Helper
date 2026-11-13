"""Win32 GDI frame source that captures only the requested ROIs."""
from __future__ import annotations

import ctypes
import os
import time
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from ..overlay import capture
from .frame import Frame, Roi, SourceState

user32 = ctypes.WinDLL("user32", use_last_error=True)
GAME_TITLE_HINTS = getattr(capture, "GAME_TITLE_HINTS", ("选技", "Skill Legends", "大乱斗"))


def _find_title_window() -> int:
    """Prefer a title-matching game window even when it is not foreground."""
    from ctypes import wintypes

    own_pid = os.getpid()
    candidates = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == own_pid:
                return True
            title = capture.window_title(hwnd)
            if not title or not any(hint.lower() in title.lower() for hint in GAME_TITLE_HINTS):
                return True
            box = capture.client_box(hwnd)
            width, height = box[2] - box[0], box[3] - box[1]
            if width >= 640 and height >= 360:
                candidates.append((width * height, int(hwnd)))
        except Exception:
            return True
        return True

    user32.EnumWindows(callback, 0)
    if not candidates:
        return 0
    candidates.sort(reverse=True)
    return candidates[0][1]


def _is_black(arr: np.ndarray) -> bool:
    return int(arr.max()) < 12 or float(arr.std()) < 4.0


class WindowFrameSource:
    def __init__(self, refresh_ms: int = 500) -> None:
        capture.enable_dpi_awareness()
        self.refresh_ms = refresh_ms
        self.hwnd = 0
        self.last_check = 0.0
        self.client_w = 0
        self.client_h = 0
        self.capture_method = "none"
        self.last_error = ""
        self.frame_id = 0

    def _refresh(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_check < self.refresh_ms / 1000.0 and self.hwnd:
            return
        self.last_check = now
        try:
            hwnd = _find_title_window()
        except Exception as exc:
            self.hwnd = 0
            self.last_error = str(exc)
            return
        if not hwnd:
            self.hwnd = 0
            self.last_error = "window_not_found"
            return
        try:
            x0, y0, x1, y1 = capture.client_box(hwnd)
        except Exception as exc:
            self.hwnd = 0
            self.last_error = str(exc)
            return
        width, height = x1 - x0, y1 - y0
        if width < 640 or height < 360:
            self.hwnd = 0
            self.last_error = "client_too_small"
            return
        if self.hwnd != hwnd or width != self.client_w or height != self.client_h:
            self.hwnd = int(hwnd)
            self.client_w, self.client_h = width, height
            self.capture_method = "none"

    def grab(self, roi: Roi) -> Optional[Frame]:
        self._refresh()
        if not self.hwnd:
            return None
        try:
            bx0, by0, bx1, by1 = capture.client_box(self.hwnd)
        except Exception as exc:
            self.last_error = str(exc)
            return None
        width, height = bx1 - bx0, by1 - by0
        rx0, rx1, ry0, ry1 = roi
        x0 = bx0 + int(round(width * rx0))
        x1 = bx0 + int(round(width * rx1))
        y0 = by0 + int(round(height * ry0))
        y1 = by0 + int(round(height * ry1))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        box = (x0, y0, x1, y1)
        arr: Optional[np.ndarray] = None
        try:
            image = capture.capture_screen(box)
            arr = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
            self.capture_method = "bitblt"
        except Exception:
            arr = None
        if arr is None or _is_black(arr):
            try:
                image = capture.capture_printwindow(self.hwnd, box)
                arr = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
                self.capture_method = "printwindow"
            except Exception as exc:
                self.last_error = str(exc)
                arr = None
        if arr is None or _is_black(arr):
            self.capture_method = "black"
            self.last_error = "black_frame"
            return None
        self.frame_id += 1
        self.last_error = ""
        return Frame(image=arr, frame_id=self.frame_id, timestamp=time.time(), roi=roi, source="window")

    def state(self) -> SourceState:
        self._refresh()
        if not self.hwnd:
            return SourceState(found=False, state="IDLE", error=self.last_error)
        foreground = capture.foreground_window() == self.hwnd
        return SourceState(
            found=True,
            foreground=foreground,
            client_w=self.client_w,
            client_h=self.client_h,
            capture_method=self.capture_method,
            state="WATCHING" if not foreground else "READY",
            error=self.last_error,
            hwnd=self.hwnd,
        )
