"""RapidOCR hero-name recognition with closed-set correction.

OCR is primary; the 16x16 glyph matcher remains the deterministic fallback for
any slot OCR cannot read confidently.  The bottom school icons are not OCR'd:
they contain no readable school name.
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

try:  # OpenCV is installed with rapidocr_onnxruntime, but keep the module usable.
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def _normalize_text(text: str) -> str:
    text = re.sub(r"[\s·•.,，。:：;；'\"“”‘’!！?？\-_/\\|]+", "", text or "")
    return text.strip()


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


class RapidOcrNameMatcher:
    def __init__(self, names: List[str]) -> None:
        self.names = list(dict.fromkeys(names))
        self._engine = None
        self._error = ""
        self._warmed = False

    # ------------------------------------------------------------------ setup
    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if self._error:
            return None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            self._warmed = True
        except Exception as exc:  # OCR is optional; glyph matcher still works.
            self._error = str(exc)
            self._engine = None
        return self._engine

    @property
    def available(self) -> bool:
        return self._get_engine() is not None

    @property
    def error(self) -> str:
        return self._error

    # -------------------------------------------------------------- detection
    def detect_plates(self, arr: np.ndarray, client_w: int) -> List[Tuple[int, int, int, int]]:
        """Detect stone nameplate rectangles in a nameplate ROI."""
        if cv2 is None:
            return []
        scale = max(0.45, min(2.5, client_w / 1800.0))
        hsv = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2HSV)
        s, v = hsv[:, :, 1], hsv[:, :, 2]
        mask = ((s < 88) & (v > 55) & (v < 232)).astype(np.uint8) * 255
        # A fixed kernel is more stable than scaling it on very wide windows;
        # scaling here merged the stone plaques into the dark background.
        kernel = np.ones((5, 25), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 70 * scale or w > 460 * scale:
                continue
            if h < 50 * scale or h > 115 * scale:
                continue
            if not (1.2 <= w / float(max(1, h)) <= 10.0):
                continue
            if w * h < 1600 * scale * scale:
                continue
            boxes.append((x, y, x + w, y + h))
        # Keep the lower nameplate row if an arch fragment sneaks in; then first 3.
        boxes.sort(key=lambda b: ((b[1] + b[3]) / 2.0, b[0]))
        if len(boxes) > 3:
            y_tol = 22 * scale
            clusters: List[List[Tuple[int, int, int, int]]] = []
            for box in boxes:
                cy = (box[1] + box[3]) / 2.0
                for cluster in clusters:
                    if abs(cy - sum((b[1] + b[3]) / 2.0 for b in cluster) / len(cluster)) < y_tol:
                        cluster.append(box)
                        break
                else:
                    clusters.append([box])
            if clusters:
                boxes = max(clusters, key=lambda c: (len(c), sum(b[2] - b[0] for b in c)))
        boxes.sort(key=lambda b: b[0])
        return boxes[:3]

    # ------------------------------------------------------------------- OCR
    def _ocr_crop(self, crop: np.ndarray) -> Tuple[str, float]:
        engine = self._get_engine()
        if engine is None:
            return "", 0.0
        image = Image.fromarray(crop.astype(np.uint8), "RGB")
        # Nameplates are small; 2x helps the recognizer and costs only a few ms.
        if image.height < 90:
            image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
        bgr = np.asarray(image, dtype=np.uint8)[:, :, ::-1]
        try:
            result, _ = engine(bgr, use_det=False, use_cls=False, use_rec=True)
        except Exception:
            return "", 0.0
        if not result:
            return "", 0.0
        best_text = ""
        best_conf = 0.0
        for item in result:
            if not item:
                continue
            if len(item) >= 3 and isinstance(item[1], str):
                text, conf = item[1], float(item[2])
            elif len(item) >= 2 and isinstance(item[0], str):
                text, conf = item[0], float(item[1])
            else:
                continue
            if conf >= best_conf:
                best_text, best_conf = text, conf
        return _normalize_text(best_text), best_conf

    def _resolve(self, text: str, confidence: float) -> Optional[str]:
        text = _normalize_text(text)
        if not text:
            return None
        if text in self.names:
            return text
        if confidence < 0.45:
            return None
        scored = sorted(
            ((difflib.SequenceMatcher(None, text, name).ratio(), name) for name in self.names),
            reverse=True,
        )
        if not scored:
            return None
        ratio, name = scored[0]
        if ratio < 0.70:
            return None
        max_distance = 0 if len(name) <= 2 else 1
        if _levenshtein(text, name) > max_distance:
            return None
        if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 1e-6:
            return None
        return name

    def match(self, nameplates: np.ndarray, client_w: int, glyph_matcher: Any) -> Dict[str, Any]:
        plates = self.detect_plates(nameplates, client_w)
        candidates: List[Optional[Dict[str, Any]]] = [None, None, None]
        if plates:
            for index, (x0, y0, x1, y1) in enumerate(plates[:3]):
                pad_x = max(2, (x1 - x0) // 20)
                pad_y = max(2, (y1 - y0) // 20)
                crop = nameplates[
                    max(0, y0 - pad_y):min(nameplates.shape[0], y1 + pad_y),
                    max(0, x0 - pad_x):min(nameplates.shape[1], x1 + pad_x),
                ]
                text, confidence = self._ocr_crop(crop)
                name = self._resolve(text, confidence)
                candidates[index] = {
                    "slot": index,
                    "name": name,
                    "score": round(float(confidence if name else 0.0), 4),
                    "unknown_hero": False,
                    "source": "ocr" if name else None,
                    "ocr_text": text,
                }
        if any(c is None or not c.get("name") for c in candidates):
            glyph = glyph_matcher.match(nameplates, self._glyph_groups(nameplates, client_w))
            for index, fallback in enumerate(glyph.get("candidates", [])[:3]):
                if candidates[index] is None or not candidates[index].get("name"):
                    candidates[index] = {
                        "slot": index,
                        "name": fallback.get("name"),
                        "score": round(float(fallback.get("score", 0.0)), 4),
                        "unknown_hero": bool(fallback.get("unknown_hero")),
                        "source": "glyph" if fallback.get("name") else None,
                        "ocr_text": "",
                    }
        for index in range(3):
            if candidates[index] is None:
                candidates[index] = {
                    "slot": index,
                    "name": None,
                    "score": 0.0,
                    "unknown_hero": False,
                    "source": None,
                    "ocr_text": "",
                }
        return {
            "candidates": candidates[:3],
            "glyph_coverage": 1.0 if self.available else 0.0,
            "missing_glyphs": [],
            "engine": "rapidocr" if self.available else "glyph",
            "ocr_error": self.error,
        }

    @staticmethod
    def _glyph_groups(nameplates: np.ndarray, client_w: int) -> List[Any]:
        from .blobs import group_nameplates, segment_glyphs

        h = int(nameplates.shape[0])
        boxes = segment_glyphs(
            nameplates,
            (0.0, 1.0, 0.0, 1.0),
            bright_percentile=72,
            min_area_scale=80,
            min_height_px=max(8, int(h * 0.025)),
        )
        return group_nameplates(boxes, client_w * 0.035, h, max_names=5)
