"""Resolution-aware template groups and cached runtime matchers.

The recognition templates were built from a 1800px-wide client area.  Windows
can be smaller or larger, so layout.json describes width buckets.  A bucket may
share the canonical files (today's state) or point at separately built files
later.  Keeping the selection here means the sampler, CLI and offline tools all
agree on which group a window belongs to.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .glyphs import GlyphMatcher
from .ocr import RapidOcrNameMatcher
from .schools import SchoolMatcher

DEFAULT_REFERENCE_WIDTH = 1800
DEFAULT_REFERENCE_HEIGHT = 1118
DEFAULT_FILES = ("schools_chroma.json", "school_runes.json", "glyphs.json")


@dataclass(frozen=True)
class TemplateGroup:
    id: str
    min_width: int
    max_width: Optional[int]
    reference_width: int
    schools: str
    runes: str
    glyphs: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TemplateGroup":
        try:
            group = cls(
                id=str(raw["id"]),
                min_width=int(raw.get("min_width", 0)),
                max_width=None if raw.get("max_width") is None else int(raw["max_width"]),
                reference_width=int(raw.get("reference_width", DEFAULT_REFERENCE_WIDTH)),
                schools=str(raw.get("schools", DEFAULT_FILES[0])),
                runes=str(raw.get("runes", DEFAULT_FILES[1])),
                glyphs=str(raw.get("glyphs", DEFAULT_FILES[2])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid template group: %r" % (raw,)) from exc
        if group.max_width is not None and group.max_width < group.min_width:
            raise ValueError("template group %s has max_width < min_width" % group.id)
        if group.reference_width <= 0:
            raise ValueError("template group %s has non-positive reference_width" % group.id)
        return group

    def contains(self, width: int) -> bool:
        return self.min_width <= int(width) and (
            self.max_width is None or int(width) <= self.max_width
        )

    def files(self) -> Tuple[str, ...]:
        return (self.schools, self.runes, self.glyphs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "min_width": self.min_width,
            "max_width": self.max_width,
            "reference_width": self.reference_width,
            "schools": self.schools,
            "runes": self.runes,
            "glyphs": self.glyphs,
        }


@dataclass(frozen=True)
class AssetBundle:
    group: TemplateGroup
    school_matcher: SchoolMatcher
    glyph_matcher: GlyphMatcher
    ocr_matcher: Optional[RapidOcrNameMatcher]


def reference_width(layout: Mapping[str, Any]) -> int:
    resolution = layout.get("reference_resolution") or {}
    raw = resolution.get("width", layout.get("reference_width", DEFAULT_REFERENCE_WIDTH))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_REFERENCE_WIDTH
    return value if value > 0 else DEFAULT_REFERENCE_WIDTH


def _groups(layout: Mapping[str, Any]) -> List[TemplateGroup]:
    raw_groups = layout.get("template_groups") or []
    if not raw_groups:
        ref = reference_width(layout)
        return [
            TemplateGroup(
                id="default",
                min_width=0,
                max_width=None,
                reference_width=ref,
                schools=DEFAULT_FILES[0],
                runes=DEFAULT_FILES[1],
                glyphs=DEFAULT_FILES[2],
            )
        ]
    return [TemplateGroup.from_dict(item) for item in raw_groups]


def select_template_group(
    layout: Mapping[str, Any],
    client_width: int,
) -> TemplateGroup:
    """Pick exactly one width bucket; 0/None means use the reference width."""
    width = int(client_width or 0)
    if width <= 0:
        width = reference_width(layout)
    for group in _groups(layout):
        if group.contains(width):
            return group
    raise ValueError("no template group covers %dpx" % width)


def missing_template_files(
    layout: Mapping[str, Any],
    base_dir: Path,
) -> List[str]:
    """Return absolute paths for every missing template referenced by layout."""
    base = Path(base_dir)
    missing: List[str] = []
    for group in _groups(layout):
        for relative in group.files():
            path = base / relative
            if not path.is_file():
                missing.append(str(path))
    return missing


class AssetCache:
    """Build matchers per template group and reuse shared files.

    Constructing GlyphMatcher from the 2MB glyph table is not free, so groups
    that point at the same files share matchers.  The OCR model does not depend
    on templates and is built once for the whole cache.
    """

    def __init__(
        self,
        layout: Mapping[str, Any],
        base_dir: Path,
        names: Sequence[str],
        *,
        use_ocr: bool = True,
    ) -> None:
        self.layout = dict(layout)
        self.base_dir = Path(base_dir)
        self.names = list(names)
        self.use_ocr = bool(use_ocr)
        self._bundles: Dict[str, AssetBundle] = {}
        self._matcher_cache: Dict[Tuple[str, str, str, int], Tuple[SchoolMatcher, GlyphMatcher]] = {}
        self._ocr_matcher: Optional[RapidOcrNameMatcher] = (
            RapidOcrNameMatcher(self.names) if self.use_ocr else None
        )

    def _load_matchers(self, group: TemplateGroup) -> Tuple[SchoolMatcher, GlyphMatcher]:
        key = (group.schools, group.runes, group.glyphs, group.reference_width)
        cached = self._matcher_cache.get(key)
        if cached is not None:
            return cached
        schools_path = self.base_dir / group.schools
        glyphs_path = self.base_dir / group.glyphs
        runes_path = self.base_dir / group.runes
        for path in (schools_path, glyphs_path):
            if not path.is_file():
                raise FileNotFoundError("template file missing: %s" % path)
        school_data = json.loads(schools_path.read_text(encoding="utf-8"))
        glyph_data = json.loads(glyphs_path.read_text(encoding="utf-8"))
        rune_data = (
            json.loads(runes_path.read_text(encoding="utf-8"))
            if runes_path.is_file()
            else None
        )
        matchers = (
            SchoolMatcher(
                school_data,
                float(self.layout.get("margin_min", 0.012)),
                runes=rune_data,
            ),
            GlyphMatcher(glyph_data, self.names),
        )
        self._matcher_cache[key] = matchers
        return matchers

    def for_width(self, client_width: int) -> AssetBundle:
        group = select_template_group(self.layout, client_width)
        bundle = self._bundles.get(group.id)
        if bundle is None:
            school_matcher, glyph_matcher = self._load_matchers(group)
            bundle = AssetBundle(
                group=group,
                school_matcher=school_matcher,
                glyph_matcher=glyph_matcher,
                ocr_matcher=self._ocr_matcher,
            )
            self._bundles[group.id] = bundle
        return bundle
