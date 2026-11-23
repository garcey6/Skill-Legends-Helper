"""Tkinter debug overlay for the live recognition pipeline.

The agent imports this module with the rest of the UI, but only constructs a
:class:`DebugOverlay` after the user enables debug mode; the production path
does no screenshot, frame or drawing work while the switch is off.
"""
from __future__ import annotations

import json
import os
import time
import tkinter as tk
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageTk

from ..vision.debugframe import DebugBox, DebugFrame


ROI_COLOR = (103, 216, 178)
OCR_COLOR = (231, 189, 97)
TEMPLATE_COLOR = (122, 167, 232)
FAIL_COLOR = (232, 112, 112)
BG_COLOR = (14, 20, 28)
TEXT_COLOR = (232, 238, 247)
DIM_COLOR = (154, 168, 184)
ALL_LAYERS = ("roi", "ocr", "templates")
LAYER_KEYS = {"1": "roi", "2": "ocr", "3": "templates"}


def user_debug_dir() -> Path:
    """User-writable debug output; never under the bundled ``data/`` tree."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "SkillLegendsHelper"
    return Path.home() / "AppData" / "Roaming" / "SkillLegendsHelper"


def position_path() -> Path:
    return user_debug_dir() / "debug_overlay.json"


def debug_output_dir() -> Path:
    return user_debug_dir() / "debug"


def _font(size: int = 12) -> ImageFont.ImageFont:
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _scaled_box(box: DebugBox, frame: DebugFrame, image: Image.Image) -> Tuple[int, int, int, int]:
    sx = image.width / max(1, frame.image_size[0])
    sy = image.height / max(1, frame.image_size[1])
    return (
        int(round(box.x * sx)),
        int(round(box.y * sy)),
        int(round(box.x1 * sx)),
        int(round(box.y1 * sy)),
    )


def _draw_label(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, color: Tuple[int, int, int], font) -> None:
    x, y = xy
    bbox = draw.textbbox((x, y), text, font=font)
    pad = 2
    draw.rectangle(
        (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
        fill=BG_COLOR,
        outline=color,
    )
    draw.text((x, y), text, font=font, fill=color)


def render_debug_image(
    image: Image.Image,
    frame: DebugFrame,
    layers: Sequence[str] = ALL_LAYERS,
) -> Image.Image:
    """Draw the same DebugFrame onto a screenshot; used by the window and PNG."""
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    visible = set(layers)
    font = _font(12)
    small = _font(10)

    specs = []
    if "roi" in visible:
        specs.extend((box, ROI_COLOR, "ROI") for box in frame.rois)
    if "ocr" in visible:
        specs.extend((box, OCR_COLOR, "OCR") for box in frame.ocr)
    if "templates" in visible:
        specs.extend((box, TEMPLATE_COLOR, "模板") for box in frame.templates)
    for box, color, kind in specs:
        x0, y0, x1, y1 = _scaled_box(box, frame, canvas)
        if x1 <= x0 or y1 <= y0:
            continue
        draw.rectangle((x0, y0, x1, y1), outline=color, width=2)
        label = box.label or kind
        if box.score:
            label = "%s %.2f" % (label, box.score)
        _draw_label(draw, (x0, max(0, y0 - 16)), label, color, small)

    # Header and footer are deliberately simple: the overlay is a debugging
    # tool, not a second HUD.
    timestamp = frame.timestamp.replace("T", " ")
    _draw_label(draw, (10, 8), "DEBUG %s" % timestamp, TEXT_COLOR, font)
    footer = "ROI 青 / OCR 金 / 模板 蓝 · 1 ROI  2 OCR  3 模板  A 全部  S 保存  Esc 关闭"
    _draw_label(draw, (10, max(0, canvas.height - 26)), footer, DIM_COLOR, small)
    if frame.failure_reason:
        reason = frame.failure_reason
        if len(reason) > 120:
            reason = reason[:117] + "..."
        _draw_label(draw, (10, 30), "失败原因：%s" % reason, FAIL_COLOR, small)
    return canvas


def save_debug_png(
    image: Image.Image,
    frame: DebugFrame,
    *,
    out_dir: Optional[Path] = None,
    layers: Sequence[str] = ALL_LAYERS,
) -> Path:
    target = Path(out_dir) if out_dir is not None else debug_output_dir()
    target.mkdir(parents=True, exist_ok=True)
    stamp = frame.timestamp.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    path = target / ("debug_%s.png" % stamp)
    render_debug_image(image, frame, layers=layers).save(path, format="PNG")
    return path


def fit_debug_image(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """Fit a full screenshot inside the work area; boxes are scaled on draw."""
    max_width = max(1, int(max_width))
    max_height = max(1, int(max_height))
    if image.width <= max_width and image.height <= max_height:
        return image.copy()
    scale = min(max_width / image.width, max_height / image.height)
    return image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )


class DebugOverlay:
    """Topmost, draggable Tk window showing one DebugFrame."""

    def __init__(
        self,
        master: tk.Misc,
        image: Image.Image,
        frame: DebugFrame,
        *,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.master = master
        self.image = image
        self.frame = frame
        self.on_close = on_close
        self._closed = False
        self.layers = set(ALL_LAYERS)
        self.visible = False
        self.last_save_path: Optional[Path] = None
        self.top = tk.Toplevel(master)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="#0e141c", cursor="fleur")
        self.canvas = tk.Canvas(self.top, bd=0, highlightthickness=0, bg="#0e141c", cursor="fleur")
        self.canvas.pack()
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo: Optional[ImageTk.PhotoImage] = None
        self._display_image = fit_debug_image(
            image,
            int(self.top.winfo_screenwidth() * 0.9),
            int(self.top.winfo_screenheight() * 0.85),
        )
        self._drag_offset = (0, 0)
        self._dragging = False
        self._saved_position = self._load_position()
        for widget in (self.top, self.canvas):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
            widget.bind("<KeyPress>", self._on_key)
        self._render()
        self.top.deiconify()
        self.top.lift()
        self.visible = True
        try:
            self.top.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------- position
    def _load_position(self) -> Optional[Tuple[int, int]]:
        try:
            data = json.loads(position_path().read_text(encoding="utf-8"))
            return int(data["x"]), int(data["y"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_position(self) -> None:
        try:
            path = position_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"x": int(self.top.winfo_x()), "y": int(self.top.winfo_y())}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _drag_start(self, event) -> None:
        self._drag_offset = (
            int(event.x_root) - int(self.top.winfo_rootx()),
            int(event.y_root) - int(self.top.winfo_rooty()),
        )
        self._dragging = True

    def _drag_move(self, event) -> None:
        if not self._dragging:
            return
        x = int(event.x_root) - self._drag_offset[0]
        y = int(event.y_root) - self._drag_offset[1]
        width = max(1, self.top.winfo_width())
        height = max(1, self.top.winfo_height())
        x = max(0, min(x, self.top.winfo_screenwidth() - width))
        y = max(0, min(y, self.top.winfo_screenheight() - height))
        self.top.geometry("+%d+%d" % (x, y))

    def _drag_end(self, _event=None) -> None:
        if self._dragging:
            self._dragging = False
            self._save_position()

    # ---------------------------------------------------------------- render
    def suspend(self) -> None:
        """Hide only for the screenshot; position and layers stay intact."""
        try:
            self.top.withdraw()
        except tk.TclError:
            pass

    def resume(self) -> None:
        try:
            self.top.deiconify()
            self.top.lift()
        except tk.TclError:
            pass

    def _render(self) -> None:
        view = render_debug_image(self._display_image, self.frame, layers=tuple(self.layers))
        self.photo = ImageTk.PhotoImage(view)
        self.canvas.config(width=view.width, height=view.height)
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        self.top.geometry("%dx%d+%d+%d" % (view.width, view.height, *self._place()))
        self.top.update_idletasks()

    def _place(self) -> Tuple[int, int]:
        width = max(1, self.top.winfo_width())
        height = max(1, self.top.winfo_height())
        if self._saved_position:
            x, y = self._saved_position
        else:
            x, y = 20, 20
        x = max(0, min(int(x), self.top.winfo_screenwidth() - width))
        y = max(0, min(int(y), self.top.winfo_screenheight() - height))
        return x, y

    def update(self, image: Image.Image, frame: DebugFrame) -> None:
        self.image = image
        self.frame = frame
        self._display_image = fit_debug_image(
            image,
            int(self.top.winfo_screenwidth() * 0.9),
            int(self.top.winfo_screenheight() * 0.85),
        )
        self._render()

    # ---------------------------------------------------------------- actions
    def _on_key(self, event) -> None:
        key = (event.keysym or "").lower()
        if key in LAYER_KEYS:
            name = LAYER_KEYS[key]
            if name in self.layers:
                self.layers.discard(name)
            else:
                self.layers.add(name)
            self._render()
        elif key == "a":
            self.layers = set(ALL_LAYERS)
            self._render()
        elif key == "s":
            self.last_save_path = save_debug_png(self.image, self.frame, layers=tuple(self.layers))
            print("调试截图已保存：%s" % self.last_save_path, flush=True)
        elif key == "escape":
            self.close()

    def save(self) -> Path:
        self.last_save_path = save_debug_png(self.image, self.frame, layers=tuple(self.layers))
        return self.last_save_path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.visible = False
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        if self.on_close is not None:
            self.on_close()
