"""Import a real game screenshot into a labeled validation/holdout set.

The importer is intentionally strict: unknown heroes, duplicate labels, tiny
images and path-like names are rejected before anything is written.  Images and
meta.json are written through temporary files so a failed import cannot leave a
case registered without its screenshot (or vice versa).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from app.kb.recommend import Advisor  # noqa: E402

DEFAULT_DATASET = ROOT / "samples" / "validation" / "holdout"
MIN_SIZE = (640, 360)
MAX_SIZE = (7680, 4320)
DEFAULT_DESCRIPTION = (
    "真实游戏窗口 holdout；每张图由 tools/import_validation.py 登记，"
    "英雄名使用正式名，流派未知可留 null。"
)


def _clean_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise ValueError("案例名不能为空")
    if name.startswith(".") or "/" in name or "\\" in name or ":" in name:
        raise ValueError("案例名不能包含路径字符：%r" % value)
    if Path(name).suffix:
        raise ValueError("案例名不要带扩展名：%r" % value)
    return name


def normalize_heroes(values: Sequence[str], advisor: Advisor) -> List[str]:
    names: List[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        hero = advisor.hero_by_name.get(value)
        if hero is None:
            for candidate in advisor.heroes:
                if value in (candidate.get("aliases") or []):
                    hero = candidate
                    break
        if hero is None:
            raise ValueError("未知英雄：%s" % value)
        canonical = hero["name"]
        if canonical in names:
            raise ValueError("重复英雄：%s" % canonical)
        names.append(canonical)
    if not names:
        raise ValueError("至少标注一个英雄")
    return names


def normalize_schools(values: Sequence[str], advisor: Advisor) -> List[str]:
    by_name = {s["name"]: s["name"] for s in advisor.schools}
    by_id = {s["id"]: s["name"] for s in advisor.schools}
    names: List[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        canonical = by_name.get(value) or by_id.get(value)
        if canonical is None:
            raise ValueError("未知流派：%s" % value)
        if canonical in names:
            raise ValueError("重复流派：%s" % canonical)
        names.append(canonical)
    return names


def _load_meta(meta_path: Path) -> Dict[str, Any]:
    if not meta_path.is_file():
        return {"description": DEFAULT_DESCRIPTION, "cases": []}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取 %s：%s" % (meta_path, exc)) from exc
    if not isinstance(meta, dict):
        raise ValueError("%s 必须是 JSON 对象" % meta_path)
    cases = meta.get("cases")
    if not isinstance(cases, list):
        raise ValueError("%s 的 cases 必须是数组" % meta_path)
    meta.setdefault("description", DEFAULT_DESCRIPTION)
    return meta


def _open_rgb(image_path: Path) -> Image.Image:
    try:
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
            if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
                raise ValueError(
                    "图片分辨率过低：%dx%d（至少 %dx%d）"
                    % (width, height, MIN_SIZE[0], MIN_SIZE[1])
                )
            if width > MAX_SIZE[0] or height > MAX_SIZE[1]:
                raise ValueError(
                    "图片分辨率过高：%dx%d（最多 %dx%d）"
                    % (width, height, MAX_SIZE[0], MAX_SIZE[1])
                )
            return image.convert("RGB")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("无法读取图片 %s：%s" % (image_path, exc)) from exc


def image_digest(image: Image.Image) -> str:
    """Hash decoded RGB pixels so JPEG/PNG encodings of one frame compare equal."""
    return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()


def _existing_digest(case: Dict[str, Any], dataset: Path) -> str:
    digest = str(case.get("sha256") or "")
    if digest:
        return digest
    client = dataset / str(case.get("client") or "")
    if not client.is_file():
        return ""
    try:
        with Image.open(client) as image:
            image.load()
            return image_digest(image)
    except Exception:
        return ""


def _same_labels(case: Dict[str, Any], heroes: Sequence[str], schools: Optional[Sequence[str]]) -> bool:
    expected = case.get("expected") or {}
    old_heroes = list(expected.get("heroes") or [])
    old_schools = expected.get("schools")
    new_schools = None if schools is None else list(schools)
    return old_heroes == list(heroes) and (old_schools or None) == new_schools


def import_case(
    image: Path,
    name: str,
    heroes: Sequence[str],
    schools: Optional[Sequence[str]],
    note: str,
    dataset: Path,
    replace: bool = False,
    advisor: Optional[Advisor] = None,
) -> Dict[str, Any]:
    """Copy one RGB screenshot and append/replace its labeled meta entry."""
    image_path = Path(image)
    dataset = Path(dataset)
    case_name = _clean_name(name)
    if not image_path.is_file():
        raise ValueError("图片不存在：%s" % image_path)

    advisor = advisor or Advisor()
    hero_names = normalize_heroes(heroes, advisor)
    school_names = None if schools is None else normalize_schools(schools, advisor)
    rgb = _open_rgb(image_path)

    dataset.mkdir(parents=True, exist_ok=True)
    meta_path = dataset / "meta.json"
    meta = _load_meta(meta_path)
    cases = list(meta.get("cases") or [])
    client_name = case_name + ".png"
    existing = next((case for case in cases if case.get("name") == case_name), None)
    if existing is not None and not replace:
        raise ValueError("案例已存在：%s（使用 --replace 覆盖）" % case_name)
    if existing is None:
        for case in cases:
            if case.get("client") == client_name:
                raise ValueError("图片名已被其他案例占用：%s" % client_name)

    digest = image_digest(rgb)
    resolution = [rgb.width, rgb.height]
    for case in cases:
        if existing is not None and case is existing:
            continue
        same_digest = _existing_digest(case, dataset) == digest
        same_size = list(case.get("resolution") or []) == resolution
        if same_digest:
            raise ValueError(
                "图片内容重复：与案例 %s 是同一帧（不要用同屏连拍充数）"
                % case.get("name")
            )
        if same_size and _same_labels(case, hero_names, school_names):
            raise ValueError(
                "尺寸与标签完全重复：与案例 %s 相同，请换一帧或改标注"
                % case.get("name")
            )

    try:
        source = str(image_path.resolve().relative_to(ROOT))
    except ValueError:
        source = str(image_path.resolve())
    case: Dict[str, Any] = {
        "name": case_name,
        "client": client_name,
        "expected": {"heroes": hero_names, "schools": school_names},
        "note": (note or "").strip(),
        "resolution": resolution,
        "sha256": digest,
        "source": source,
    }
    if existing is None:
        cases.append(case)
    else:
        cases = [case if item.get("name") == case_name else item for item in cases]
    meta["cases"] = cases

    destination = dataset / client_name
    tmp_image = dataset / (".%s.png.tmp" % case_name)
    tmp_meta = dataset / ".meta.json.tmp"
    try:
        rgb.save(tmp_image, format="PNG")
        tmp_meta.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_image, destination)
        os.replace(tmp_meta, meta_path)
    finally:
        for path in (tmp_image, tmp_meta):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    return case


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="完整客户区截图（PNG/JPG）")
    parser.add_argument("--name", required=True, help="案例名，例如 holdout_001")
    parser.add_argument("--heroes", required=True, help="逗号分隔的英雄名，可写别名")
    parser.add_argument("--schools", default="", help="逗号分隔的流派名或 id；未知留空")
    parser.add_argument("--note", default="", help="分辨率、窗口模式等备注")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--replace", action="store_true", help="覆盖同名案例")
    args = parser.parse_args(argv)

    heroes = [item.strip() for item in args.heroes.split(",") if item.strip()]
    schools = [item.strip() for item in args.schools.split(",") if item.strip()]
    try:
        case = import_case(
            args.image,
            args.name,
            heroes,
            schools or None,
            args.note,
            args.dataset,
            replace=args.replace,
        )
    except ValueError as exc:
        print("导入失败：%s" % exc, file=sys.stderr)
        return 2
    meta = json.loads((args.dataset / "meta.json").read_text(encoding="utf-8"))
    print(
        "已导入 %s（%dx%d，%d 个英雄），当前共 %d 组。"
        % (
            case["name"],
            case["resolution"][0],
            case["resolution"][1],
            len(case["expected"]["heroes"]),
            len(meta["cases"]),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
