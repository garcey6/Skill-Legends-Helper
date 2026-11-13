"""Automatic live sampler with separate capture and recognition threads."""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from .frame import FrameSource, SourceState
from .stability import diff_ratio, drop_cursor_frames, is_still, median_stack
from ..vision.blobs import segment_runs
from ..vision.pipeline import recognize_rois


CaptureItem = Tuple[SourceState, np.ndarray, np.ndarray, Dict[str, Any], float]


class LiveSampler:
    def __init__(
        self,
        source: FrameSource,
        layout: Dict[str, Any],
        school_matcher: Any,
        glyph_matcher: Any,
        callback: Callable[[str, Optional[Dict[str, Any]]], None],
        *,
        ocr_matcher: Any = None,
        interval_ms: int = 250,
        before_capture: Optional[Callable[[], None]] = None,
        after_capture: Optional[Callable[[], None]] = None,
    ) -> None:
        self.source = source
        self.layout = layout
        self.school_matcher = school_matcher
        self.glyph_matcher = glyph_matcher
        self.ocr_matcher = ocr_matcher
        self.callback = callback
        self.before_capture = before_capture
        self.after_capture = after_capture
        self.interval = max(0.05, interval_ms / 1000.0)
        self._stop = threading.Event()
        self._force = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._recognition_thread: Optional[threading.Thread] = None
        self._queue: "queue.Queue[Optional[CaptureItem]]" = queue.Queue(maxsize=2)
        self._last_fingerprint = ""
        self._last_icons: Optional[np.ndarray] = None
        self._last_names: Optional[np.ndarray] = None
        self._state = "IDLE"
        self._last_state_report = ""

    def start(self) -> None:
        if self._capture_thread and self._capture_thread.is_alive():
            return
        self._stop.clear()
        self._recognition_thread = threading.Thread(
            target=self._recognition_loop, name="live-recognition", daemon=True
        )
        self._capture_thread = threading.Thread(
            target=self._capture_loop, name="live-capture", daemon=True
        )
        self._recognition_thread.start()
        self._capture_thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

    def force(self) -> None:
        self._force.set()

    def _emit(self, state: str, result: Optional[Dict[str, Any]] = None, force: bool = False) -> None:
        if state != self._last_state_report or force:
            self._last_state_report = state
            try:
                self.callback(state, result)
            except Exception:
                pass

    def _probe_runs(self, icons: np.ndarray, client_w: int) -> list:
        # Cheap probe: stride 2, no PIL resize.  Stride 4 loses narrow runs at
        # 900-1280px client widths, so keep 2 and accept ~1ms extra.
        small = icons[::2, ::2]
        return segment_runs(
            small,
            (0.0, 1.0, 0.0, 1.0),
            sat_th=int(self.layout.get("sat_th", 40)),
            min_width=max(2, int(float(self.layout.get("min_run_w", 20)) * client_w / 1800.0 / 2)),
        )

    def _clear_round(self) -> None:
        self._last_fingerprint = ""
        self._last_icons = None
        self._last_names = None

    def _capture_loop(self) -> None:
        icons_roi = tuple(self.layout["rois"]["icons"])
        names_roi = tuple(self.layout["rois"]["nameplates"])
        n = int(self.layout.get("stability", {}).get("n", 5))
        interval = float(self.layout.get("stability", {}).get("frame_interval_ms", 15)) / 1000.0
        while not self._stop.is_set():
            state = self.source.state()
            if not state.found:
                self._clear_round()
                self._emit("IDLE")
                self._stop.wait(0.5)
                continue
            started = time.perf_counter()
            icons_frame = self.source.grab(icons_roi)
            if icons_frame is None:
                self._emit("DEGRADED")
                self._stop.wait(0.7)
                continue
            grab_ms = (time.perf_counter() - started) * 1000.0
            runs = self._probe_runs(icons_frame.image, state.client_w or icons_frame.image.shape[1])
            if len(runs) != int(self.layout.get("expected_enabled", 8)):
                self._clear_round()
                self._emit("WATCHING")
                self._stop.wait(self.interval)
                continue
            name_probe = self.source.grab(names_roi)
            if name_probe is None:
                self._emit("DEGRADED")
                self._stop.wait(0.7)
                continue
            if (
                self._last_icons is not None
                and self._last_names is not None
                and not self._force.is_set()
                and diff_ratio(icons_frame.image, self._last_icons) < 0.008
                and diff_ratio(name_probe.image, self._last_names) < 0.008
            ):
                self._state = "READY"
                self._emit("READY")
                self._stop.wait(0.8)
                continue

            self._state = "CAPTURING"
            icon_frames = [icons_frame.image]
            name_frames = [name_probe.image]
            if self.before_capture is not None:
                try:
                    self.before_capture()
                except Exception:
                    pass
            try:
                for _ in range(n - 1):
                    if self._stop.is_set():
                        return
                    time.sleep(interval)
                    icon_frame = self.source.grab(icons_roi)
                    name_frame = self.source.grab(names_roi)
                    if icon_frame is None or name_frame is None:
                        continue
                    icon_frames.append(icon_frame.image)
                    name_frames.append(name_frame.image)
            finally:
                if self.after_capture is not None:
                    try:
                        self.after_capture()
                    except Exception:
                        pass
            if len(icon_frames) < 3 or len(name_frames) < 3:
                self._emit("DEGRADED")
                self._stop.wait(0.7)
                continue
            icon_frames, drop_icons = drop_cursor_frames(icon_frames)
            name_frames, drop_names = drop_cursor_frames(name_frames)
            icon_stack = median_stack(icon_frames)
            name_stack = median_stack(name_frames)
            still, diffs = is_still(icon_frames)
            if not still:
                self._emit("CAPTURING")
                self._stop.wait(self.interval)
                continue
            stability = {
                "frames_used": len(icon_frames),
                "diff_ratios": [round(v, 4) for v in diffs[-3:]],
                "still": still,
                "dropped_frames": len(drop_icons) + len(drop_names),
                "drop_reasons": sorted(set(drop_icons + drop_names)),
            }
            item: CaptureItem = (
                state,
                icon_stack,
                name_stack,
                stability,
                round(grab_ms, 2),
            )
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    pass
            self._stop.wait(0.15)

    def _recognition_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                return
            state, icon_stack, name_stack, stability, grab_ms = item
            started = time.perf_counter()
            try:
                result = recognize_rois(
                    icon_stack,
                    name_stack,
                    (state.client_w, state.client_h),
                    self.layout,
                    self.school_matcher,
                    self.glyph_matcher,
                    self.ocr_matcher,
                )
            except Exception:
                self._emit("DEGRADED")
                continue
            total = (time.perf_counter() - started) * 1000.0
            result["session"]["state"] = "READY"
            result["session"]["capture_method"] = state.capture_method
            result["stability"] = stability
            timings = result.setdefault("timings_ms", {})
            timings["grab"] = grab_ms
            timings["aggregate"] = round(float(self.layout.get("stability", {}).get("frame_interval_ms", 15)) * max(1, stability["frames_used"] - 1), 2)
            timings["total"] = round(float(timings.get("total", total)) + grab_ms, 2)
            if result["schools"].get("status") == "ok":
                fingerprint = "|".join(result["schools"]["enabled"]) + "#" + "|".join(
                    str(c.get("name")) for c in result["heroes"].get("candidates", [])
                )
                changed = fingerprint != self._last_fingerprint or self._force.is_set()
                self._last_fingerprint = fingerprint
                self._last_icons = icon_stack.copy()
                self._last_names = name_stack.copy()
                self._force.clear()
                self._state = "READY"
                self._emit("READY", result, force=changed)
            else:
                self._state = "DEGRADED"
                self._emit("DEGRADED", result)
            self._stop.wait(0.05)
