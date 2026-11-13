"""Replay and single-image frame sources for offline regression."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from .frame import Frame, Roi, SourceState


class ImageFrameSource:
    def __init__(self, path: str | Path) -> None:
        image = Image.open(path).convert("RGB")
        self.array = np.asarray(image, dtype=np.uint8).copy()
        self.width, self.height = image.size
        self.frame_id = 0
        self.state_value = SourceState(found=True, client_w=self.width, client_h=self.height, state="READY")

    def grab(self, roi: Roi) -> Optional[Frame]:
        h, w = self.array.shape[:2]
        x0, x1, y0, y1 = roi
        crop = self.array[int(h * y0):int(h * y1), int(w * x0):int(w * x1)].copy()
        self.frame_id += 1
        return Frame(crop, self.frame_id, time.time(), roi, "image")

    def state(self) -> SourceState:
        return self.state_value


class ReplayFrameSource:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.files = sorted(self.directory.glob("*.png"))
        if not self.files:
            raise FileNotFoundError("no PNG frames in %s" % directory)
        self.meta = {}
        meta_path = self.directory / "meta.json"
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        first = Image.open(self.files[0])
        self.width, self.height = first.size
        self.index = 0
        self.frame_id = 0
        self.state_value = SourceState(found=True, client_w=self.width, client_h=self.height, state="READY")
        self._array = np.asarray(first.convert("RGB"), dtype=np.uint8).copy()

    def _load(self) -> None:
        path = self.files[self.index % len(self.files)]
        self._array = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8).copy()

    def grab(self, roi: Roi) -> Optional[Frame]:
        self._load()
        h, w = self._array.shape[:2]
        x0, x1, y0, y1 = roi
        crop = self._array[int(h * y0):int(h * y1), int(w * x0):int(w * x1)].copy()
        self.frame_id += 1
        frame = Frame(crop, self.frame_id, time.time(), roi, "replay")
        self.index += 1
        return frame

    def state(self) -> SourceState:
        return self.state_value
