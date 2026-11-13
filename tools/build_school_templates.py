"""Build color-chroma templates for the 13 schools from the shipped icons."""
from __future__ import annotations

import colorsys
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.blobs import segment_runs  # noqa: E402
from app.vision.chroma import chroma  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "recognize"
SCHOOL_ICONS = DATA / "templates" / "schools"


def main() -> int:
    schools = json.loads((DATA / "schools.json").read_text(encoding="utf-8"))["schools"]
    by_name = {s["name"]: s for s in schools}
    templates = []
    for sid in ["basic", "dodge", "crit", "life", "heal", "ultimate", "poison", "freeze", "shield", "vulnerable", "spirit", "rage", "haste"]:
        path = SCHOOL_ICONS / (sid + ".png")
        if not path.exists():
            raise SystemExit("missing school icon: %s" % path)
        image = Image.open(path).convert("RGB")
        arr = np.asarray(image, dtype=np.int16)
        h, w = arr.shape[:2]
        half = max(4, int(min(w, h) * 0.28))
        vec = chroma(arr, w // 2, h // 2, half)
        if vec is None:
            raise SystemExit("no chroma signal for %s" % sid)
        r, g, b = [float(v) for v in vec]
        hue = colorsys.rgb_to_hsv(r, g, b)[0] * 360.0
        meta = by_name.get(
            {
                "basic": "普攻流", "dodge": "闪避流", "crit": "暴击流", "life": "生命流",
                "heal": "回复流", "ultimate": "大招流", "poison": "中毒流", "freeze": "冰冻流",
                "shield": "护盾流", "vulnerable": "易伤流", "spirit": "精灵流", "rage": "怒气流",
                "haste": "急速流",
            }[sid],
            {},
        )
        templates.append(
            {
                "id": sid,
                "name": meta.get("name", sid),
                "chroma": [round(v, 6) for v in vec.tolist()],
                "hue_deg": round(hue, 1),
                "variants": [[round(v, 6) for v in vec.tolist()]],
            }
        )

    # Add clean bottom-strip variants from the known sample frames.  Banned
    # panel icons contain the red ring, so the bottom strip is the better colour
    # reference for a school that is enabled in that frame.
    variant_sets = [
        ("samples/draft_001.png", ["basic", "heal", "ultimate", "poison", "shield", "spirit", "rage", "haste"]),
        ("samples/window_draft.png", ["dodge", "crit", "heal", "ultimate", "freeze", None, "rage", "haste"]),
    ]
    by_id = {item["id"]: item for item in templates}
    layout = json.loads((DATA / "recognize" / "layout.json").read_text(encoding="utf-8"))
    for rel, labels in variant_sets:
        path = ROOT / rel
        if not path.exists():
            continue
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
        runs = segment_runs(arr, layout["rois"]["icons"], layout["sat_th"], layout["min_run_w"])
        if len(runs) != 8:
            continue
        cy = int(np.median([r["cy"] for r in runs]))
        width = float(np.median([r["w"] for r in runs]))
        half = max(4, int(round(layout["base_half"] * width / layout["base_run_w"])))
        for run, sid in zip(runs, labels):
            if not sid or sid not in by_id:
                continue
            vec = chroma(arr, int(run["cx"]), cy, half)
            if vec is None:
                continue
            rounded = [round(float(v), 6) for v in vec.tolist()]
            if rounded not in by_id[sid]["variants"]:
                by_id[sid]["variants"].append(rounded)

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "data/templates/schools/*.png",
        "base_run_w": 55.0,
        "base_half": 15.0,
        "templates": templates,
    }
    (OUT / "schools_chroma.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", OUT / "schools_chroma.json", "templates", len(templates))
    for item in templates:
        print(" ", item["id"], item["name"], item["hue_deg"], item["chroma"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
