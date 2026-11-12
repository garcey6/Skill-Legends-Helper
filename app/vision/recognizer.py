"""Screenshot recognition for 选技大乱斗 draft screens.

The UI uses a fixed layout: five stone nameplates in the top row (three heroes,
a locked slot and a random slot) and a school panel in the lower right with a
4-column grid.  Recognition is template based, so it works fully offline:

* school identity  -> the white 3-character label next to each icon
* banned / enabled -> the red "no" ring drawn around banned icons
* hero identity    -> the portrait inside the stone arch
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from ..config import (
    HEROES_PATH,
    HERO_TEMPLATE_DIR,
    SCHOOL_TEMPLATE_DIR,
    SCHOOLS_PATH,
    TEMPLATE_DIR,
    load_json,
    save_json,
)
from . import imageops as iops
from .imageops import Box

# Reference geometry measured on a 1800px-wide screenshot.
SLOT_X = (0.0783, 0.3188, 0.5582, 0.7976)
SLOT_Y = (0.2548, 0.4154, 0.7366, 0.8972)
SLOT_ORDER = [(r, c) for r in range(4) for c in range(4)]
SLOT_ORDER = SLOT_ORDER[:8] + SLOT_ORDER[8:13]

HERO_FALLBACK_PLATES = [
    (0.0289, 0.4007, 0.1467, 0.0644),
    (0.2267, 0.4007, 0.1467, 0.0644),
    (0.4244, 0.4007, 0.1467, 0.0644),
    (0.6222, 0.4007, 0.1467, 0.0644),
    (0.8178, 0.4007, 0.1467, 0.0644),
]

LABEL_SIZE = (150, 44)
HERO_FEAT_SIZE = (96, 128)


def _safe_int(v: float) -> int:
    return int(round(float(v)))


class Recognizer:
    def __init__(self, reference_width: int = 1800) -> None:
        self.reference_width = int(reference_width)
        self.schools: List[Dict[str, Any]] = []
        self.school_by_id: Dict[str, Dict[str, Any]] = {}
        self.heroes: List[Dict[str, Any]] = []
        self.label_templates: Dict[str, Any] = {}
        self.icon_templates: Dict[str, np.ndarray] = {}
        self.hero_templates: List[Tuple[str, np.ndarray]] = []
        self.reload()

    # ---------------------------------------------------------------- loading
    def reload(self) -> None:
        data = load_json(SCHOOLS_PATH, {}) or {}
        self.schools = data.get("schools", [])
        self.school_by_id = {s["id"]: s for s in self.schools}
        heroes = load_json(HEROES_PATH, {}) or {}
        self.heroes = heroes.get("heroes", [])
        self.label_templates = {}
        self.icon_templates = {}
        for school in self.schools:
            sid = school["id"]
            label_path = SCHOOL_TEMPLATE_DIR / (sid + "_label.png")
            if label_path.exists():
                try:
                    self.label_templates[sid] = label_feature(Image.open(label_path).convert("RGB"))
                except Exception:
                    pass
            icon_path = SCHOOL_TEMPLATE_DIR / (sid + ".png")
            if icon_path.exists():
                try:
                    img = Image.open(icon_path).convert("RGB").resize((56, 56), Image.LANCZOS)
                    self.icon_templates[sid] = np.asarray(img, dtype=np.float32)
                except Exception:
                    pass
        self.hero_templates = []
        for hero in self.heroes:
            portrait = hero.get("portrait")
            if not portrait:
                continue
            path = Path(portrait)
            if not path.is_absolute():
                # portraits are stored relative to the app root
                path = HEROES_PATH.parent.parent / portrait
            if not path.exists():
                continue
            try:
                self.hero_templates.append((hero["name"], hero_feature(Image.open(path).convert("RGB"))))
            except Exception:
                continue

    # ------------------------------------------------------------- detection
    def _detect_panel(self, im: Image.Image) -> Optional[Box]:
        arr = np.asarray(im, dtype=np.int16)
        h, w = arr.shape[:2]
        mask = iops.gray_mask(arr)
        start = int(h * 0.42)
        rows: List[Tuple[int, int, int]] = []
        for y in range(start, int(h * 0.97), 2):
            xs = np.nonzero(mask[y, int(w * 0.32):])[0]
            if xs.size < w * 0.18:
                continue
            x0 = int(xs.min()) + int(w * 0.32)
            x1 = int(xs.max()) + int(w * 0.32)
            if x1 - x0 > w * 0.30:
                rows.append((y, x0, x1))
        if len(rows) < 20:
            return None
        # contiguous row segments
        segments: List[List[Tuple[int, int, int]]] = []
        for row in rows:
            if segments and row[0] - segments[-1][-1][0] <= 8:
                segments[-1].append(row)
            else:
                segments.append([row])
        segment = max(segments, key=len)
        if len(segment) < h * 0.12:
            return None
        ys = [r[0] for r in segment]
        lefts = sorted(r[1] for r in segment)
        rights = sorted(r[2] for r in segment)
        x0 = lefts[len(lefts) // 2]
        x1 = rights[len(rights) // 2]
        y0 = min(ys) - 6
        y1 = max(ys) + 8
        if x1 - x0 < w * 0.3 or y1 - y0 < h * 0.2:
            return None
        return (max(0, x0), max(0, y0), min(w, x1), min(h, y1))

    def _detect_nameplates(self, im: Image.Image) -> List[Box]:
        arr = np.asarray(im, dtype=np.int16)
        h, w = arr.shape[:2]
        mask = iops.gray_mask(arr)
        top = mask[: int(h * 0.55), :]
        small = iops.block_any(top, 4)
        comps = iops.components(small, min_area=80)
        boxes: List[Box] = []
        for x0, y0, x1, y1, area in comps:
            x0 *= 4
            x1 *= 4
            y0 *= 4
            y1 *= 4
            bw = x1 - x0
            bh = y1 - y0
            if not (w * 0.10 <= bw <= w * 0.23):
                continue
            if not (h * 0.035 <= bh <= h * 0.085):
                continue
            if bw / float(max(1, bh)) < 2.4:
                continue
            if y0 < h * 0.30:
                continue
            boxes.append((x0, y0, x1, y1))
        # Nameplates all share one horizontal band; the stone arch also yields a
        # couple of wide gray blobs higher up, so cluster by y and keep the
        # largest cluster instead of trusting every candidate.
        boxes.sort(key=lambda b: b[1])
        clusters: List[List[Box]] = []
        for b in boxes:
            cy = (b[1] + b[3]) / 2.0
            for cluster in clusters:
                cy0 = sum((c[1] + c[3]) / 2.0 for c in cluster) / len(cluster)
                if abs(cy - cy0) < h * 0.025:
                    cluster.append(b)
                    break
            else:
                clusters.append([b])
        clusters.sort(key=len, reverse=True)
        chosen = sorted(clusters[0], key=lambda b: b[0]) if clusters else []
        merged: List[Box] = []
        for b in chosen:
            if merged and b[0] < merged[-1][2] - 10:
                if (b[2] - b[0]) > (merged[-1][2] - merged[-1][0]):
                    merged[-1] = b
                continue
            merged.append(b)
        if len(merged) < 3:
            return [self._fallback_plate(i, w, h) for i in range(5)]
        return merged[:5]

    def _fallback_plate(self, index: int, w: int, h: int) -> Box:
        fx, fy, fw, fh = HERO_FALLBACK_PLATES[index]
        return (_safe_int(fx * w), _safe_int(fy * h), _safe_int((fx + fw) * w), _safe_int((fy + fh) * h))

    @staticmethod
    def _hero_portrait_box(plate: Box) -> Box:
        x0, y0, x1, y1 = plate
        nw = x1 - x0
        return (
            _safe_int(x0 + 0.22 * nw),
            _safe_int(y0 - 0.95 * nw),
            _safe_int(x0 + 0.78 * nw),
            _safe_int(y0 - 0.10 * nw),
        )

    # -------------------------------------------------------------- matching
    def _match_hero(self, crop_img: Image.Image) -> Tuple[str, float, List[Dict[str, Any]]]:
        feat = hero_feature(crop_img)
        scored = []
        for name, templ in self.hero_templates:
            scored.append((name, iops.ncc(feat, templ)))
        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored:
            return "", 0.0, []
        top = scored[:3]
        best_name, best_score = top[0]
        if best_score < 0.80:
            best_name = ""
        return best_name, round(best_score, 4), [{"name": n, "score": round(s, 4)} for n, s in top]

    def _detect_ban_rings(self, im: Image.Image) -> List[Tuple[int, int, int, int, int]]:
        arr = np.asarray(im, dtype=np.int16)
        h, w = arr.shape[:2]
        mask = iops.red_mask(arr)
        mask[: int(h * 0.45), :] = False
        mask[:, : int(w * 0.40)] = False
        rings = []
        for x0, y0, x1, y1, area in iops.components(mask, min_area=400):
            bw = x1 - x0
            bh = y1 - y0
            if 50 <= bw <= 74 and 50 <= bh <= 74 and 0.80 <= bw / float(bh) <= 1.25:
                rings.append((x0, y0, x1, y1, area))
        return rings

    def _grid_from_rings(self, rings: List[Tuple[int, int, int, int, int]]) -> Optional[List[Tuple[float, float]]]:
        """Recover all 13 slot centres from the five red ban rings.

        The five banned schools are always laid out in the last five grid
        cells: four in one row, one in the next row.  Their red rings give us
        the four column centres plus the two lower row centres, from which the
        two enabled rows follow at a fixed pitch.
        """
        if len(rings) != 5:
            return None
        rings = sorted(rings, key=lambda r: ((r[1] + r[3]) / 2.0, (r[0] + r[2]) / 2.0))
        top = [r for r in rings if abs((r[1] + r[3]) / 2.0 - (rings[0][1] + rings[0][3]) / 2.0) < 20]
        bottom = [r for r in rings if r not in top]
        if len(top) != 4 or len(bottom) != 1:
            return None
        top.sort(key=lambda r: (r[0] + r[2]) / 2.0)
        xs = [(r[0] + r[2]) / 2.0 for r in top]
        row2_y = sum((r[1] + r[3]) / 2.0 for r in top) / 4.0
        row3_y = (bottom[0][1] + bottom[0][3]) / 2.0
        unit = row3_y - row2_y
        if not (30 <= unit <= 140):
            return None
        # sanity: even spacing across columns
        gaps = [xs[i + 1] - xs[i] for i in range(3)]
        if not gaps or max(gaps) - min(gaps) > 20:
            return None
        row1_y = row2_y - 2 * unit
        row0_y = row1_y - unit
        centers = []
        for y in (row0_y, row1_y, row2_y, row3_y):
            for x in xs:
                centers.append((x, y))
        return centers[:13]

    def _match_schools(self, im: Image.Image, panel: Box) -> Tuple[List[Dict[str, Any]], str]:
        arr = np.asarray(im, dtype=np.int16)
        px0, py0, px1, py1 = panel
        pw = px1 - px0
        ph = py1 - py0
        rings = self._detect_ban_rings(im)
        centers = self._grid_from_rings(rings)
        grid_method = "ban_rings"
        if centers is None:
            grid_method = "panel_fallback"
            centers = []
            for row in range(4):
                for col in range(4):
                    centers.append((px0 + SLOT_X[col] * pw, py0 + SLOT_Y[row] * ph))
            centers = centers[:13]
        results: List[Optional[Dict[str, Any]]] = []
        for slot_index, (cx, cy) in enumerate(centers):
            row = min(3, slot_index // 4)
            col = slot_index % 4
            label_box = (
                _safe_int(cx + 34),
                _safe_int(cy - 30),
                _safe_int(min(im.width, cx + 210)),
                _safe_int(cy + 30),
            )
            crop_img = iops.crop(im, label_box)
            feat = label_feature(crop_img)
            scored = []
            if feat is not None:
                for sid, templ in self.label_templates.items():
                    if templ is None:
                        continue
                    score = sum(iops.ncc(feat[k], templ[k]) for k in range(2)) / 2.0
                    scored.append((sid, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            results.append(
                {
                    "slot": slot_index,
                    "row": row,
                    "col": col,
                    "center": (cx, cy),
                    "label_box": label_box,
                    "scores": scored,
                }
            )

        # Greedy one-to-one assignment (13 slots, 13 schools).
        pairs: List[Tuple[float, int, str]] = []
        for idx, item in enumerate(results):
            for sid, score in item["scores"][:6]:
                pairs.append((score, idx, sid))
        pairs.sort(reverse=True)
        assigned: Dict[int, Tuple[str, float]] = {}
        used = set()
        for score, idx, sid in pairs:
            if idx in assigned or sid in used:
                continue
            assigned[idx] = (sid, score)
            used.add(sid)
        # fill any missing assignment with the slot's best remaining guess
        for idx, item in enumerate(results):
            if idx in assigned:
                continue
            for sid, score in item["scores"]:
                if sid not in used:
                    assigned[idx] = (sid, score)
                    used.add(sid)
                    break

        for idx, item in enumerate(results):
            sid, score = assigned.get(idx, ("", 0.0))
            item["school_id"] = sid
            item["confidence"] = round(float(score), 4)
            icon_crop = iops.crop(
                im,
                (
                    _safe_int(item["center"][0] - 44),
                    _safe_int(item["center"][1] - 44),
                    _safe_int(item["center"][0] + 44),
                    _safe_int(item["center"][1] + 44),
                ),
            )
            red = np.asarray(icon_crop, dtype=np.int16)
            item["red_ratio"] = float(iops.red_mask(red).mean()) if red.size else 0.0
            item["icon"] = "/data/templates/schools/%s.png" % sid if sid else ""

        # When the red rings calibrated the grid we already know the layout:
        # slots 0-7 are enabled and slots 8-12 are banned.  Otherwise fall back
        # to red-pixel ranking (the game always bans exactly five).
        if grid_method == "ban_rings":
            for item in results:
                item["banned"] = item["slot"] >= 8
                item["ban_confidence"] = "high"
        else:
            ranked = sorted(results, key=lambda item: item["red_ratio"], reverse=True)
            banned_ids = {item["slot"] for item in ranked[:5]}
            for item in results:
                by_threshold = item["red_ratio"] >= 0.06
                item["banned"] = item["slot"] in banned_ids
                item["ban_confidence"] = "high" if by_threshold == item["banned"] else "low"
        return results, grid_method

    # ------------------------------------------------------------------ API
    def analyze(self, im: Image.Image, debug: bool = False) -> Dict[str, Any]:
        warnings: List[str] = []
        original_size = im.size
        im = im.convert("RGB")
        im, scale = iops.fit_width(im, self.reference_width)
        arr = np.asarray(im, dtype=np.int16)

        panel = self._detect_panel(im)
        panel_found = panel is not None
        if panel is None:
            warnings.append("未能定位流派面板，请手动确认启用/禁用流派。")
            panel = (
                _safe_int(im.width * 0.46),
                _safe_int(im.height * 0.46),
                _safe_int(im.width * 0.995),
                _safe_int(im.height * 0.93),
            )

        school_slots: List[Dict[str, Any]] = []
        grid_method = "none"
        if panel_found and self.label_templates:
            school_slots, grid_method = self._match_schools(im, panel)
        if not self.label_templates:
            warnings.append("缺少流派标签模板，请先运行 tools/build_templates.py。")
        if len(school_slots) != 13:
            warnings.append("流派识别不完整，请手动确认。")
        low_conf = [s for s in school_slots if s["confidence"] < 0.70]
        if low_conf:
            warnings.append("有 %d 个流派名称识别置信度偏低，请核对。" % len(low_conf))

        plates = self._detect_nameplates(im)
        if len(plates) < 3:
            warnings.append("英雄名牌识别不足 3 个，已使用默认布局兜底。")
        heroes = []
        for idx, plate in enumerate(plates[:3]):
            box = self._hero_portrait_box(plate)
            portrait = iops.crop(im, box)
            name, score, top3 = self._match_hero(portrait)
            if not name:
                warnings.append("第 %d 个英雄未匹配到已知模板，请手动选择。" % (idx + 1))
            heroes.append(
                {
                    "slot": idx,
                    "name": name,
                    "confidence": round(float(score), 4),
                    "box": list(box),
                    "portrait": iops.image_to_data_url(portrait, "PNG"),
                    "top": top3,
                }
            )

        enabled = [s for s in school_slots if not s["banned"]]
        banned = [s for s in school_slots if s["banned"]]
        if len(enabled) != 8 or len(banned) != 5:
            warnings.append("流派数量异常（启用 %d / 禁用 %d），建议手动修正。" % (len(enabled), len(banned)))

        def school_payload(item: Dict[str, Any]) -> Dict[str, Any]:
            meta = self.school_by_id.get(item["school_id"], {})
            return {
                "id": item["school_id"],
                "name": meta.get("name", item["school_id"]),
                "short": meta.get("short", meta.get("name", "")),
                "color": meta.get("color", "#9aa4b2"),
                "icon": item["icon"],
                "confidence": item["confidence"],
                "banned": item["banned"],
                "red_ratio": round(item["red_ratio"], 4),
            }

        boxes = []
        for h in heroes:
            boxes.append((tuple(h["box"]), (92, 200, 140), "HERO %d" % (h["slot"] + 1)))
        for s in school_slots:
            color = (220, 80, 80) if s["banned"] else (226, 186, 80)
            # keep the annotation on the icon so the school name stays readable
            boxes.append(
                (
                    (
                        _safe_int(s["center"][0] - 36),
                        _safe_int(s["center"][1] - 36),
                        _safe_int(s["center"][0] + 36),
                        _safe_int(s["center"][1] + 36),
                    ),
                    color,
                    "",
                )
            )
        annotated = iops.draw_boxes(im, boxes)

        payload: Dict[str, Any] = {
            "diagnostics": {
                "panel_found": panel_found,
                "nameplates": len(plates),
                "matched_heroes": sum(1 for h in heroes if h["name"]),
                "schools": len(school_slots),
            },
            "image": {
                "width": original_size[0],
                "height": original_size[1],
                "preview": iops.image_to_data_url(annotated, "JPEG", max_width=1400, quality=86),
            },
            "heroes": heroes,
            "schools": {
                "enabled": [school_payload(s) for s in enabled],
                "banned": [school_payload(s) for s in banned],
            },
            "panel": list(panel),
            "warnings": warnings,
        }
        if debug:
            payload["debug"] = {
                "scale": scale,
                "reference_size": list(im.size),
                "panel": list(panel),
                "grid_method": grid_method,
                "nameplates": [list(p) for p in plates],
                "slots": [
                    {
                        "slot": s["slot"],
                        "best": s["school_id"],
                        "score": s["confidence"],
                        "red": round(s["red_ratio"], 4),
                        "top": [[sid, round(sc, 3)] for sid, sc in s["scores"][:3]],
                    }
                    for s in school_slots
                ],
            }
        return payload

    # ---------------------------------------------------------------- learning
    def learn_hero(self, name: str, portrait_data_url: str) -> Dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("英雄名称不能为空")
        hero = self.find_hero(name)
        if hero is None:
            hero = {
                "id": "user_%s" % str(abs(hash(name)) % 10_000_000),
                "name": name,
                "aliases": [],
                "role": "待补充",
                "difficulty": 2,
                "tier": "B",
                "power": 70,
                "schools": {},
                "weak_to": [],
                "summary": "用户标注的英雄，尚未录入攻略。",
                "portrait": "",
                "source": "用户标注",
            }
            self.heroes.append(hero)
        raw = iops.decode_data_url(portrait_data_url)
        img = iops.open_image(raw)
        HERO_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        path = HERO_TEMPLATE_DIR / (hero["id"] + ".png")
        img.save(path, format="PNG")
        hero["portrait"] = "data/templates/heroes/%s.png" % hero["id"]
        hero["updated"] = date.today().isoformat()
        data = load_json(HEROES_PATH, {"heroes": self.heroes}) or {"heroes": self.heroes}
        data["heroes"] = self.heroes
        save_json(HEROES_PATH, data)
        self.reload()
        return hero

    def find_hero(self, value: str) -> Optional[Dict[str, Any]]:
        value = (value or "").strip()
        if not value:
            return None
        for hero in self.heroes:
            if value == hero.get("name") or value in (hero.get("aliases") or []):
                return hero
        for hero in self.heroes:
            if value and (value in hero.get("name", "") or hero.get("name", "") in value):
                return hero
        return None


# ------------------------------------------------------------------ features
def hero_feature(im: Image.Image) -> np.ndarray:
    return iops.sharpen_for_match(im, HERO_FEAT_SIZE)


def label_feature(im: Image.Image) -> Optional[List[np.ndarray]]:
    """Return normalized 2-cell features of the first two Chinese characters.

    All school labels are exactly three characters, so the trailing "流" is
    identical everywhere.  Comparing only the first two glyphs removes that
    shared noise and makes matching much more discriminative.
    """
    if im.width < 20 or im.height < 10:
        return None
    arr = np.asarray(im.convert("RGB"), dtype=np.int16)
    mask = iops.white_mask(arr, lo=190, spread=45)
    comps = iops.components(mask, min_area=40)
    # Chinese glyphs are bevelled: one character often breaks into several
    # white components, so we keep every reasonably sized component instead of
    # filtering by height.  The crop starts to the right of the icon, so there
    # is no icon contamination.
    comps = [c for c in comps if (c[3] - c[1]) >= 6 and (c[2] - c[0]) >= 4]
    if not comps:
        return None
    x0 = min(c[0] for c in comps)
    x1 = max(c[2] for c in comps)
    y0 = min(c[1] for c in comps)
    y1 = max(c[3] for c in comps)
    if x1 - x0 < 40 or y1 - y0 < 20:
        return None
    # pad, then resize to a canonical 3-character strip
    pad_x, pad_y = 8, 6
    box = (max(0, x0 - pad_x), max(0, y0 - pad_y), min(im.width, x1 + pad_x), min(im.height, y1 + pad_y))
    strip = mask[box[1]:box[3], box[0]:box[2]]
    strip_img = Image.fromarray((strip * 255).astype(np.uint8)).resize(LABEL_SIZE, Image.BILINEAR)
    vals = np.asarray(strip_img, dtype=np.float32) / 255.0
    cells = [vals[:, i * (LABEL_SIZE[0] // 3):(i + 1) * (LABEL_SIZE[0] // 3)] for i in range(3)]
    feats = []
    for cell in cells[:2]:
        v = cell - cell.mean()
        v /= (np.linalg.norm(v) + 1e-6)
        feats.append(v)
    return feats


def school_icon_url(school_id: str) -> str:
    return "/data/templates/schools/%s.png" % school_id
