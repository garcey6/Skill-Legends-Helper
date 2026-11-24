"""Minimal Tkinter fixture annotator.

Run from the repository root::

    python tools/annotate_fixture.py --image tests/fixtures/screenshots/draft001_1800x1118.png

Drag a rectangle, name it, then press ``s`` to merge the normalized features
into the sibling expected JSON.  The image is never modified.
"""
from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Dict, Iterable, Optional, Tuple

from PIL import Image, ImageTk

from app.vision.annotation import Annotation, Feature, PixelBox, update_expected_annotation

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPECTED = ROOT / "tests" / "fixtures" / "expected"


class AnnotationEditor:
    """Testable rectangle state shared by the Tk canvas and save path."""

    def __init__(self, image_size: Tuple[int, int], features: Iterable[Feature] = ()) -> None:
        self.width, self.height = image_size
        self.rects: Dict[str, PixelBox] = {
            feature.name: feature.to_pixels(self.width, self.height) for feature in features
        }

    def add_rect(self, name: str, rect: PixelBox) -> None:
        name = name.strip()
        if not name:
            raise ValueError("feature name must not be empty")
        if name in self.rects:
            raise ValueError("feature already exists: %s" % name)
        candidate = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        self._validate_rect(name, candidate)
        self.rects[name] = candidate

    def remove(self, name: str) -> None:
        self.rects.pop(name, None)

    def _validate_rect(self, name: str, rect: PixelBox) -> None:
        if rect[2] <= 0 or rect[3] <= 0:
            raise ValueError("feature %s has no area" % name)
        if rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > self.width or rect[1] + rect[3] > self.height:
            raise ValueError("feature %s is outside the image" % name)

    def _validate(self) -> None:
        for name, rect in self.rects.items():
            self._validate_rect(name, rect)

    def annotation(self) -> Annotation:
        self._validate()
        return Annotation.from_rects((self.width, self.height), self.rects)


class AnnotationTool:
    def __init__(self, root: tk.Tk, image_path: Path, expected_path: Path) -> None:
        self.root = root
        self.image_path = Path(image_path)
        self.expected_path = Path(expected_path)
        self.image = Image.open(self.image_path).convert("RGB")
        self.editor = AnnotationEditor(self.image.size, self._existing_features())
        self._drag_start: Optional[Tuple[int, int]] = None
        self._preview: Optional[int] = None
        self._fit_scale = min(1.0, 1200 / self.image.width, 800 / self.image.height)
        display_size = (
            max(1, int(self.image.width * self._fit_scale)),
            max(1, int(self.image.height * self._fit_scale)),
        )
        self.display = self.image.resize(display_size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(self.display)
        self.canvas = tk.Canvas(root, width=display_size[0], height=display_size[1], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        root.bind("s", lambda _event: self.save())
        root.bind("<BackSpace>", lambda _event: self._remove_last())
        root.bind("<Escape>", lambda _event: root.destroy())
        self._draw()
        root.title("标注 %s — 拖拽框选，s 保存，Backspace 撤销" % self.image_path.name)

    def _existing_features(self) -> Iterable[Feature]:
        if not self.expected_path.is_file():
            return ()
        payload = json.loads(self.expected_path.read_text(encoding="utf-8"))
        raw = payload.get("annotation")
        if not raw:
            return ()
        return Annotation.from_dict(raw).features

    def _on_press(self, event: tk.Event) -> None:
        self._drag_start = (int(event.x), int(event.y))
        if self._preview is not None:
            self.canvas.delete(self._preview)
        self._preview = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#67d8b2", width=2
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_start is None or self._preview is None:
            return
        self.canvas.coords(self._preview, self._drag_start[0], self._drag_start[1], event.x, event.y)

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_start is None or self._preview is None:
            return
        start_x, start_y = self._drag_start
        self._drag_start = None
        self.canvas.delete(self._preview)
        self._preview = None
        left = min(start_x, int(event.x))
        top = min(start_y, int(event.y))
        right = max(start_x, int(event.x))
        bottom = max(start_y, int(event.y))
        if right - left < 6 or bottom - top < 6:
            return
        name = simpledialog.askstring("特征名称", "例如 icons / nameplates / hero_slot_1", parent=self.root)
        if not name:
            return
        rect = self._display_to_image((left, top, right - left, bottom - top))
        try:
            self.editor.add_rect(name, rect)
        except ValueError as exc:
            messagebox.showerror("无效框", str(exc), parent=self.root)
            return
        self._draw()

    def _display_to_image(self, rect: PixelBox) -> PixelBox:
        scale = self._fit_scale
        return (
            int(round(rect[0] / scale)),
            int(round(rect[1] / scale)),
            max(1, int(round(rect[2] / scale))),
            max(1, int(round(rect[3] / scale))),
        )

    def _draw(self) -> None:
        self.canvas.delete("annotation")
        for name, rect in self.editor.rects.items():
            left = int(rect[0] * self._fit_scale)
            top = int(rect[1] * self._fit_scale)
            right = int((rect[0] + rect[2]) * self._fit_scale)
            bottom = int((rect[1] + rect[3]) * self._fit_scale)
            self.canvas.create_rectangle(
                left, top, right, bottom, outline="#e7bd61", width=2, tags="annotation"
            )
            self.canvas.create_text(
                left + 4,
                max(10, top - 8),
                anchor="w",
                text=name,
                fill="#e7bd61",
                tags="annotation",
            )

    def _remove_last(self) -> None:
        if self.editor.rects:
            self.editor.remove(list(self.editor.rects)[-1])
            self._draw()

    def save(self) -> None:
        annotation = self.editor.annotation()
        update_expected_annotation(self.expected_path, annotation)
        self.root.title("已保存 %s" % self.expected_path.name)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal normalized fixture annotator")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--expected", type=Path, default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    image_path = args.image.resolve()
    expected = args.expected or DEFAULT_EXPECTED / (image_path.stem + ".json")
    root = tk.Tk()
    AnnotationTool(root, image_path, expected)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
