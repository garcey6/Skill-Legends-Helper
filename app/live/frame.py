"""Frame-source abstraction for live and replay recognition."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Sequence, Tuple

import numpy as np

Roi = Tuple[float, float, float, float]  # x0, x1, y0, y1 (relative)


@dataclass
class Frame:
    image: np.ndarray
    frame_id: int
    timestamp: float
    roi: Roi = (0.0, 1.0, 0.0, 1.0)
    source: str = "window"


@dataclass
class SourceState:
    found: bool = False
    foreground: bool = False
    client_w: int = 0
    client_h: int = 0
    capture_method: str = "none"
    state: str = "IDLE"
    error: str = ""
    hwnd: int = 0


@dataclass
class ReplayMeta:
    client_w: int = 1800
    client_h: int = 1118
    enabled: list = field(default_factory=list)
    banned: list = field(default_factory=list)
    heroes: list = field(default_factory=list)


class FrameSource(Protocol):
    def grab(self, roi: Roi) -> Optional[Frame]: ...
    def state(self) -> SourceState: ...
