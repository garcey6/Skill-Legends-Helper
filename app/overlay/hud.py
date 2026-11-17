"""The in-game floating HUD.

The card is rendered with Pillow into a single image and shown in a borderless,
topmost Tk window.  The window is draggable and remembers its position; keeping
the visuals out of Tk widgets makes the layout predictable and avoids focus
stealing from the game.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from ..config import BASE_DIR
from . import capture

WIDTH = 620
HEIGHT = 560
HEADER_H = 150
SECTION_H = 190
SCHOOLS_H = 150
FOOTER_H = 30
POSITION_PATH = BASE_DIR / "data" / "overlay_position.json"
BG = (14, 20, 28)
PANEL = (20, 28, 38)
PANEL_2 = (24, 33, 44)
BORDER = (43, 55, 70)
GOLD = (231, 189, 97)
GOLD_DIM = (176, 139, 66)
TEXT = (233, 238, 246)
MUTED = (147, 160, 176)
DIM = (104, 118, 134)
TEAL = (103, 216, 178)
RED = (226, 118, 118)
BLUE = (122, 167, 232)

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_FALLBACK = r"C:\Windows\Fonts\simhei.ttf"

_font_cache: Dict[Tuple[int, bool], ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    candidates = [FONT_BOLD if bold else FONT_REG, FONT_FALLBACK]
    for path in candidates:
        try:
            if os.path.exists(path):
                font = ImageFont.truetype(path, size)
                _font_cache[key] = font
                return font
        except Exception:
            continue
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> List[str]:
    text = " ".join((text or "").split())
    if not text:
        return []
    lines: List[str] = []
    line = ""
    truncated = False
    for ch in text:
        trial = line + ch
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = ch
            if len(lines) >= max_lines:
                truncated = True
                break
    if line and len(lines) < max_lines:
        lines.append(line)
    elif line and len(lines) >= max_lines:
        truncated = True
    if truncated and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines[:max_lines]


def _chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: Tuple[int, int, int], enabled: bool) -> int:
    font = _font(11)
    width = int(draw.textlength(text, font=font)) + 30
    fill = (20, 42, 38) if enabled else (44, 27, 30)
    border = (43, 82, 70) if enabled else (86, 50, 54)
    draw.rounded_rectangle([x, y, x + width, y + 24], radius=8, fill=fill, outline=border, width=1)
    draw.ellipse([x + 8, y + 9, x + 14, y + 15], fill=color)
    draw.text((x + 19, y + 5), text, font=font, fill=TEXT)
    return width


def _skill_icon(path: str, size: Tuple[int, int] = (18, 18)) -> Optional[Image.Image]:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    try:
        if candidate.exists():
            icon = Image.open(candidate).convert("RGBA")
            icon.thumbnail(size, Image.LANCZOS)
            return icon
    except Exception:
        return None
    return None


def _rarity_color(rarity: int) -> Tuple[int, int, int]:
    if rarity >= 3:
        return GOLD
    if rarity == 2:
        return (122, 167, 232)
    return (156, 166, 180)


def _card_chip(draw: ImageDraw.ImageDraw, x: int, y: int, card: Dict[str, Any]) -> int:
    font = _font(10, True)
    name = str(card.get("name", ""))
    color = _rarity_color(int(card.get("rarity") or 1))
    width = int(draw.textlength(name, font=font)) + 34
    draw.rounded_rectangle([x, y, x + width, y + 24], radius=8, fill=(25, 32, 43), outline=color, width=1)
    draw.ellipse([x + 8, y + 9, x + 14, y + 15], fill=color)
    draw.text((x + 18, y + 5), name, font=font, fill=TEXT)
    return width


def _portrait(path: str, size: Tuple[int, int]) -> Image.Image:
    width, height = size
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = BASE_DIR / candidate
        try:
            if candidate.exists():
                source = Image.open(candidate).convert("RGB")
                scale = max(width / source.width, height / source.height)
                resized = source.resize((max(1, int(source.width * scale)), max(1, int(source.height * scale))), Image.LANCZOS)
                left = (resized.width - width) // 2
                top = (resized.height - height) // 2
                return resized.crop((left, top, left + width, top + height))
        except Exception:
            pass
    placeholder = Image.new("RGB", size, (18, 25, 34))
    draw = ImageDraw.Draw(placeholder)
    draw.rectangle([0, 0, width - 1, height - 1], outline=BORDER, width=1)
    draw.text((width // 2, height // 2), "?", font=_font(36, True), fill=DIM, anchor="mm")
    return placeholder


def _rounded_image(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.width - 1, image.height - 1], radius=radius, fill=255)
    output = Image.new("RGB", image.size, BG)
    output.paste(image, (0, 0), mask)
    return output


def viewport_crop(image: Image.Image, offset: int, max_height: int) -> Tuple[Image.Image, int]:
    """Crop one viewport from a tall card and clamp the scroll offset."""
    height = max(1, min(int(max_height), image.height))
    max_offset = max(0, image.height - height)
    offset = max(0, min(int(offset), max_offset))
    if height >= image.height:
        return image.copy(), 0
    return image.crop((0, offset, image.width, offset + height)), offset


def _common_header(draw: ImageDraw.ImageDraw, title: str, right: str = "") -> None:
    draw.rectangle([0, 0, WIDTH, 3], fill=GOLD)
    draw.text((22, 16), title, font=_font(12, True), fill=GOLD_DIM)
    if right:
        draw.text((WIDTH - 22, 17), right, font=_font(11), fill=DIM, anchor="ra")


def render_ready(
    settings_url: str,
    capture_key: str = "F8",
    toggle_key: str = "F9",
    quit_key: str = "Ctrl+Alt+Q",
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, 160), BG)
    draw = ImageDraw.Draw(image)
    _common_header(draw, "选技大乱斗 · 浮窗助手", "拖动 · %s 隐藏" % toggle_key)
    draw.text((22, 44), "浮窗已就绪", font=_font(24, True), fill=TEXT)
    draw.text(
        (22, 82),
        "%s 识别     %s 显示/隐藏     %s 退出" % (capture_key, toggle_key, quit_key),
        font=_font(12, True),
        fill=GOLD,
    )
    draw.text((22, 112), "设置与攻略库：" + settings_url, font=_font(10), fill=DIM)
    draw.text((22, 134), "按住卡片任意位置拖动；游戏请使用无边框窗口", font=_font(9), fill=DIM)
    return image


def render_loading(message: str = "正在读取屏幕…", toggle_key: str = "F9") -> Image.Image:
    image = Image.new("RGB", (WIDTH, 168), BG)
    draw = ImageDraw.Draw(image)
    _common_header(draw, "选技大乱斗 · 浮窗助手", "拖动 · %s 隐藏" % toggle_key)
    draw.text((22, 58), message, font=_font(22, True), fill=TEXT)
    draw.text((22, 96), "正在定位英雄与流派，请稍候", font=_font(12), fill=MUTED)
    for index in range(3):
        x = 22 + index * 18
        draw.rounded_rectangle([x, 128, x + 12, 134], radius=3, fill=GOLD if index == 0 else GOLD_DIM)
    return image


def render_error(
    message: str,
    hint: str = "",
    capture_key: str = "F8",
    toggle_key: str = "F9",
    quit_key: str = "Ctrl+Alt+Q",
) -> Image.Image:
    image = Image.new("RGB", (WIDTH, 250), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH, 3], fill=RED)
    draw.text((22, 16), "选技大乱斗 · 浮窗助手", font=_font(12, True), fill=RED)
    draw.text((WIDTH - 22, 17), "拖动 · %s 隐藏" % toggle_key, font=_font(10), fill=DIM, anchor="ra")
    draw.text((22, 50), "没有读到选人界面", font=_font(24, True), fill=TEXT)
    lines = _wrap(draw, message, _font(12), WIDTH - 44, 3)
    y = 92
    for line in lines:
        draw.text((22, y), line, font=_font(12), fill=MUTED)
        y += 21
    if hint:
        hint_lines = _wrap(draw, hint, _font(11), WIDTH - 44, 3)
        y += 6
        for line in hint_lines:
            draw.text((22, y), line, font=_font(11), fill=DIM)
            y += 19
    draw.text(
        (22, 208),
        "%s 重试     %s 隐藏     %s 退出" % (capture_key, toggle_key, quit_key),
        font=_font(11, True),
        fill=GOLD,
    )
    return image


def _render_hero_section(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    card: Dict[str, Any],
    y: int,
    index: int,
) -> None:
    """One complete hero block; every hero gets the same level of detail."""
    portrait = _portrait(card.get("art") or card.get("portrait", ""), (54, 66))
    image.paste(_rounded_image(portrait, 10), (22, y + 6))
    draw.rectangle([22, y + 6, 75, y + 71], outline=(54, 68, 86), width=1)

    name = str(card.get("name", ""))
    draw.text((86, y + 2), name, font=_font(22, True), fill=TEXT)
    name_width = draw.textlength(name, font=_font(22, True))
    tier = str(card.get("tier", "?"))
    tier_x = 86 + int(name_width) + 8
    draw.rounded_rectangle([tier_x, y + 8, tier_x + 30, y + 26], radius=5, fill=(40, 34, 22), outline=(92, 74, 40), width=1)
    draw.text((tier_x + 15, y + 17), tier, font=_font(10, True), fill=GOLD, anchor="mm")
    rank = "首选" if index == 0 else "第 %d" % (index + 1)
    draw.text((WIDTH - 24, y + 4), rank, font=_font(10, True), fill=GOLD if index == 0 else DIM, anchor="ra")
    draw.text((WIDTH - 24, y + 28), str(card.get("score", 0)), font=_font(30, True), fill=GOLD, anchor="ra")
    draw.text((WIDTH - 24, y + 60), "分", font=_font(9), fill=DIM, anchor="ra")

    role = str(card.get("role", ""))
    schools = (card.get("build") or {}).get("schools") or []
    route = " + ".join(schools[:2])
    meta_line = role + (" · 路线 " + route if route else "")
    draw.text((86, y + 34), meta_line, font=_font(11), fill=MUTED)
    if not card.get("has_guide"):
        draw.text((86, y + 50), "暂无完整攻略，结论仅供参考", font=_font(9), fill=(206, 160, 98))

    reasons = card.get("reasons") or []
    reason_text = "  ".join(str(r).rstrip("。；") for r in reasons[:2])
    lines = _wrap(draw, reason_text, _font(10), WIDTH - 108, 2)
    for line_index, line in enumerate(lines):
        draw.text((86, y + 68 + line_index * 15), line, font=_font(10), fill=(203, 213, 225))

    core_cards = card.get("core_cards") or []
    draw.text((22, y + 92), "核心卡", font=_font(9, True), fill=GOLD_DIM)
    if core_cards:
        x = 22
        for item in core_cards[:3]:
            x += _card_chip(draw, x, y + 108, item) + 5
        effect = _wrap(draw, str(core_cards[0].get("desc", "")), _font(8.5), WIDTH - 44, 1)
        if effect:
            draw.text((22, y + 136), "· " + effect[0], font=_font(8.5), fill=MUTED)
    else:
        draw.text((22, y + 108), "暂无卡牌数据", font=_font(9), fill=DIM)

    build_steps = (card.get("build") or {}).get("steps") or []
    opening = [step for step in build_steps if not str(step).startswith("主路线") and not str(step).startswith("副路线")]
    opening_line = str(opening[0]) if opening else "前 3 回合先补生存，4~10 回合集中堆主系。"
    lines = _wrap(draw, opening_line, _font(9), WIDTH - 44, 1)
    if lines:
        draw.text((22, y + 156), "开局 · " + lines[0], font=_font(9), fill=MUTED)

    talent = _skill_icon(card.get("talent_icon", ""), (16, 16))
    if talent is not None:
        image.paste(talent, (WIDTH - 74, y + 88), talent)
    ultimate = _skill_icon(card.get("ultimate_icon", ""), (16, 16))
    if ultimate is not None:
        image.paste(ultimate, (WIDTH - 44, y + 88), ultimate)

    draw.line([22, y + SECTION_H - 10, WIDTH - 22, y + SECTION_H - 10], fill=BORDER, width=1)


def render_result(
    result: Dict[str, Any],
    meta: Optional[capture.CaptureResult] = None,
    warning: str = "",
    capture_key: str = "F8",
    toggle_key: str = "F9",
    quit_key: str = "Ctrl+Alt+Q",
) -> Image.Image:
    cards = result.get("recommendations") or []
    if not cards:
        return render_error(
            "没有可推荐的英雄。",
            "请确认截图包含完整的选人界面。",
            capture_key,
            toggle_key,
            quit_key,
        )

    height = HEADER_H + SECTION_H * len(cards) + SCHOOLS_H + FOOTER_H + 12
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)
    _common_header(draw, "选技大乱斗 · 浮窗助手", "拖动 · %s 隐藏" % toggle_key)
    if warning:
        draw.text((WIDTH - 22, 38), warning, font=_font(9), fill=(206, 160, 98), anchor="ra")

    for index, card in enumerate(cards):
        _render_hero_section(draw, image, card, 44 + index * SECTION_H, index)

    school_y = HEADER_H + SECTION_H * len(cards) + 4
    enabled = (result.get("draft") or {}).get("enabled") or []
    banned = (result.get("draft") or {}).get("banned") or []
    draw.text((22, school_y), "启用 8", font=_font(10, True), fill=TEAL)
    x = 22
    y = school_y + 18
    for school in enabled:
        width = _chip(draw, x, y, str(school.get("name", "")), TEAL, True)
        x += width + 6

    draw.text((22, school_y + 54), "禁用 5", font=_font(10, True), fill=RED)
    x = 22
    y = school_y + 72
    for school in banned:
        width = _chip(draw, x, y, str(school.get("name", "")), RED, False)
        x += width + 6

    footer_y = height - 24
    draw.line([22, footer_y - 8, WIDTH - 22, footer_y - 8], fill=BORDER, width=1)
    draw.text((22, footer_y), "%s 重新识别    %s 退出" % (capture_key, quit_key), font=_font(9), fill=DIM)
    right = ""
    if meta is not None:
        right = "%s · %.2fs · %d×%d" % (meta.method, meta.elapsed, meta.image.width, meta.image.height)
    draw.text((WIDTH - 22, footer_y), right, font=_font(8), fill=DIM, anchor="ra")
    return image


class Hud:
    def __init__(
        self,
        alpha: float = 0.97,
        scale: Optional[float] = None,
        capture_key: str = "F8",
        toggle_key: str = "F9",
        quit_key: str = "Ctrl+Alt+Q",
    ) -> None:
        self.capture_key = capture_key
        self.toggle_key = toggle_key
        self.quit_key = quit_key
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", alpha)
        self.root.configure(bg="#0e141c", cursor="fleur")
        # Canvas is a normal Tk drawing widget: it displays the rendered Pillow
        # card and reliably receives mouse events for dragging.
        self.canvas = tk.Canvas(self.root, bd=0, highlightthickness=0, bg="#0e141c", cursor="fleur")
        self.canvas.pack()
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.root.withdraw()
        self.root.update_idletasks()
        # A 620px card is comfortable at 1080p; scale it up on 1440p/1600p
        # monitors so the text stays readable without changing the layout code.
        screen_width = self.root.winfo_screenwidth()
        self.scale = float(scale) if scale else max(1.0, min(1.3, screen_width / 1920.0))
        self.hwnd = capture.top_level_hwnd(self.root.winfo_id())
        capture.apply_overlay_styles(self.hwnd)
        self.visible = False
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.last_image: Optional[Image.Image] = None
        self.last_source: Optional[Image.Image] = None
        self.last_position: Tuple[int, int] = (0, 0)
        self.saved_position: Optional[Tuple[int, int]] = self._load_position()
        self._drag_offset: Tuple[int, int] = (0, 0)
        self._dragging = False
        self._full_image: Optional[Image.Image] = None
        self._scroll_offset = 0
        self._viewport_height = 0
        self._game_hwnd: Optional[int] = None
        for widget in (self.root, self.canvas):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_end)
        for widget in (self.root, self.canvas):
            widget.bind("<MouseWheel>", self._on_mousewheel)

    # ------------------------------------------------------------- position
    def _load_position(self) -> Optional[Tuple[int, int]]:
        try:
            data = json.loads(POSITION_PATH.read_text(encoding="utf-8"))
            return int(data["x"]), int(data["y"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_position(self) -> None:
        try:
            POSITION_PATH.parent.mkdir(parents=True, exist_ok=True)
            POSITION_PATH.write_text(
                json.dumps({"x": int(self.last_position[0]), "y": int(self.last_position[1])}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _drag_start(self, event) -> None:
        self._drag_offset = (
            int(event.x_root) - int(self.root.winfo_rootx()),
            int(event.y_root) - int(self.root.winfo_rooty()),
        )
        self._dragging = True

    def _drag_move(self, event) -> None:
        if not self._dragging:
            return
        x = int(event.x_root) - self._drag_offset[0]
        y = int(event.y_root) - self._drag_offset[1]
        left, top, right, bottom = capture.monitor_work_area(self.hwnd)
        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        x = max(left, min(x, right - width))
        y = max(top, min(y, bottom - height))
        self.root.geometry("+%d+%d" % (x, y))
        self.last_position = (x, y)
        self.saved_position = (x, y)

    def _drag_end(self, _event=None) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._save_position()

    def _place(self, image: Image.Image, game_hwnd: Optional[int] = None) -> Tuple[int, int]:
        left, top, right, bottom = capture.monitor_work_area(game_hwnd)
        work_h = bottom - top
        if self.saved_position:
            x = max(left, min(int(self.saved_position[0]), right - image.width))
            y = max(top, min(int(self.saved_position[1]), bottom - image.height))
        else:
            x = right - image.width - 20
            y = top + max(20, (work_h - image.height) // 2 - 20)
            if y + image.height > bottom - 20:
                y = max(top + 20, bottom - image.height - 20)
        # A tall multi-hero card must not cover the bottom icon strip while the
        # sampler is probing.  Start it at the top; the viewport is already
        # capped below the icons.
        if image.height > work_h * 0.6:
            y = top + 20
        self.saved_position = (x, y)
        self.root.geometry("%dx%d+%d+%d" % (image.width, image.height, x, y))
        self.last_position = (x, y)
        return x, y

    def _on_mousewheel(self, event) -> str:
        if self._full_image is None or self._full_image.height <= self._viewport_height:
            return "break"
        step = -60 if event.delta > 0 else 60
        max_offset = max(0, self._full_image.height - self._viewport_height)
        self._scroll_offset = max(0, min(max_offset, self._scroll_offset + step))
        self._render_viewport()
        return "break"

    def _render_viewport(self) -> None:
        if self._full_image is None:
            return
        view, offset = viewport_crop(self._full_image, self._scroll_offset, self._viewport_height)
        self._scroll_offset = offset
        if view.height < self._full_image.height:
            hint = view.copy()
            draw = ImageDraw.Draw(hint)
            draw.rounded_rectangle(
                [WIDTH - 112, view.height - 24, WIDTH - 10, view.height - 6],
                radius=6,
                fill=(14, 20, 28),
                outline=BORDER,
                width=1,
            )
            draw.text((WIDTH - 61, view.height - 15), "滚轮查看全部", font=_font(8.5), fill=DIM, anchor="mm")
            view = hint
        self.last_image = view
        self.photo = ImageTk.PhotoImage(view)
        self.canvas.config(width=view.width, height=view.height)
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        x, y = self._place(view, self._game_hwnd)
        self.root.deiconify()
        self.root.update_idletasks()
        capture.apply_overlay_styles(self.hwnd)
        capture.position_topmost(self.hwnd, x, y, view.width, view.height)
        self.visible = True

    def show(self, image: Image.Image, game_hwnd: Optional[int] = None) -> None:
        self.last_source = image
        self._game_hwnd = game_hwnd
        if self.scale and abs(self.scale - 1.0) > 0.01:
            image = image.resize(
                (max(1, int(round(image.width * self.scale))), max(1, int(round(image.height * self.scale)))),
                Image.LANCZOS,
            )
        self._full_image = image
        left, top, right, bottom = capture.monitor_work_area(game_hwnd)
        self._viewport_height = min(image.height, max(300, bottom - top - 260))
        self._scroll_offset = 0
        self._render_viewport()

    def hide(self) -> None:
        self.root.withdraw()
        self.visible = False

    def toggle(self, game_hwnd: Optional[int] = None) -> None:
        if self.visible:
            self.hide()
            return
        image = self.last_source or render_ready(
            "http://127.0.0.1:8777", self.capture_key, self.toggle_key, self.quit_key
        )
        self.show(image, game_hwnd)

    def show_ready(self, url: str) -> None:
        self.show(render_ready(url, self.capture_key, self.toggle_key, self.quit_key))

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass
