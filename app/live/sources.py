"""M1 compatibility names for capture sources.

``FrameSource`` and ``ImageFrameSource`` predate the M1 replay work.  These
aliases let replay code describe a capture source without forking the live
input abstraction.  Keep this module free of business logic; if the names are
ever unified, remove the aliases in a dedicated change.
"""
from __future__ import annotations

from .frame import FrameSource
from .replaysrc import ImageFrameSource

CaptureSource = FrameSource
StaticFrameSource = ImageFrameSource

__all__ = ["CaptureSource", "StaticFrameSource"]
