"""按步骤核对Excel原表、攻略卡池、文档链接与原项目知识库兼容性。"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

import openpyxl


# 步骤1：定位仓库；只读取指定的资料文件，不修改原始表格和应用数据库。
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data"
SOURCE_FILES = {
    name: SNAPSHOT / name for name in ("heroes.json", "cards.json", "schools.json", "rules.json")
}
SOURCE_FILES.update({
    name: SNAPSHOT / "source" / name
    for name in ("游戏规则.txt", "卡牌库.xlsx", "选技英雄数据.xlsx")
})


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value):
    """步骤2：与仓库导入规则一致，仅清除文本空白，不改技能数值。"""
    return re.sub(r"\s+", "", str(value)) if value is not None else ""


def main():
    # 步骤3：接收应用路径；默认核对当前仓库安装的知识库。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT, help="应用根目录，默认当前仓库")
    args = parser.parse_args()
    card_data = read_json(SNAPSHOT / "cards.json")
    cards = {c["id"]: c for c in card_data["cards"]}
    heroes = {h["name"]: h for h in read_json(SNAPSHOT / "heroes.json")["heroes"]}
    schools = {s["id"]: s for s in read_json(SNAPSHOT / "schools.json")["schools"]}
    builds = read_json(ROOT / "data/hero_builds.json")["builds"]
    audit = read_json(ROOT / "data/build_audit.json")
    failures = []
    checks = 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    # 步骤4：检查保存快照的哈希，防止生成后输入已被无意改动。
    for name, digest in audit["source_hashes"].items():
        check(hashlib.sha256(SOURCE_FILES[name].read_bytes()).hexdigest() == digest,
              "快照哈希改变：" + name)

    # 步骤5：逐位核对60位英雄的六项属性、天赋和大招，而不是仅数行数。
    workbook = openpyxl.load_workbook(SOURCE_FILES["选技英雄数据.xlsx"], data_only=True, read_only=True)
    hero_rows = [r for r in workbook["Sheet1"].iter_rows(min_row=2, values_only=True) if clean(r[0])]
    check(len(hero_rows) == len(heroes) == 60, "英雄总量不是60")
    for row in hero_rows:
        hero = heroes.get(clean(row[0]))
        check(hero is not None, "原表英雄未导入：" + clean(row[0]))
        if hero is None:
            continue
        for column, field in enumerate(("hp", "attack", "attack_speed", "energy_regen", "dodge", "crit"), 1):
            check(hero["stats"][field] == (row[column] or 0), f"{hero['name']}属性不一致：{field}")
        check(hero["talent"] == clean(row[7]), hero["name"] + "天赋不一致")
        check(hero["ultimate"] == clean(row[8]), hero["name"] + "大招不一致")
    workbook.close()

    # 步骤6：从Excel核对卡牌ID、品阶、双系归属、总量、基础值和原始模板。
    workbook = openpyxl.load_workbook(SOURCE_FILES["卡牌库.xlsx"], data_only=True, read_only=True)
    card_rows = [r for r in workbook["卡牌数据库"].iter_rows(min_row=2, values_only=True) if clean(r[1])]
    check(len(card_rows) == len(cards) == 156, "卡牌总量不是156")
    for row in card_rows:
        card = cards.get(int(row[0]))
        check(card is not None, "原表卡牌未导入：" + str(row[0]))
        if card is None:
            continue
        expected = {
            "name": clean(row[1]), "rarity": int(row[2]), "pool": int(row[5]),
            "base_value": float(row[6]) if row[6] is not None else None,
            "desc_template": clean(row[7]),
            "faction_ids": [card_data["meta"]["faction_map"][str(int(x))] for x in row[3:5] if x is not None],
        }
        for field, value in expected.items():
            check(card[field] == value, f"卡牌{card['id']}不一致：{field}")
    for row in workbook["流派ID分配表"].iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        sid = card_data["meta"]["faction_map"][str(int(row[0]))]
        check(schools[sid]["name"] == clean(row[1]) and schools[sid]["faction_id"] == row[0], "流派映射错误：" + sid)
    workbook.close()

    # 步骤7：核对每篇攻略的完整候选池和双系去重，防止漏牌或把共享牌算两次。
    check(len(builds) == 60 and {b["hero"] for b in builds} == set(heroes), "构筑未覆盖全部英雄")
    for build in builds:
        combined = set()
        for sid, rarity_pools in build["pools"].items():
            for rarity, count in ((1, 14), (2, 3), (3, 1)):
                ids = [r["id"] for r in rarity_pools[str(rarity)]]
                expected = {cid for cid, card in cards.items() if sid in card["faction_ids"] and card["rarity"] == rarity}
                check(len(ids) == count and set(ids) == expected, f"{build['hero']}的{sid}/{rarity}候选池缺失或重复")
                combined.update(ids)
        check(len(combined) == 35 and combined == set(build["unique_card_ids"]), build["hero"] + "合并卡池不符")
        check(Counter(cards[cid]["rarity"] for cid in combined) == {1: 27, 2: 6, 3: 2}, build["hero"] + "合并品阶数量不符")
        check(len(build["shared_card_ids"]) == 1, build["hero"] + "共享卡数量不符")
        check(set(build["focus"]) <= combined, build["hero"] + "核心卡不在候选池")

    # 步骤8：检查攻略及入口文档相对链接；外部网页保留来源，不在离线核查中验证网页可用性。
    link_count = 0
    markdown_files = list((ROOT / "data/guides").glob("*.md"))
    markdown_files += list((ROOT / "docs/流派卡池").glob("*.md"))
    markdown_files += [ROOT / "README.md"]
    markdown_files += [ROOT / "docs" / name for name in (
        "全英雄构筑速查.md", "规则与数据核对.md", "社区来源与版本差异.md",
        "网站版与浮窗助手版完整教程.md", "攻略知识库维护README.md")]
    markdown_files = [p for p in markdown_files if p.is_file()]
    for path in markdown_files:
        body = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]\n]+\]\(([^)]+)\)", body):
            parts = urlsplit(target.strip("<>"))
            if parts.scheme or parts.netloc or not parts.path:
                continue
            link_count += 1
            check((path.parent / unquote(parts.path)).resolve().is_file(), f"断开的文档链接：{path.name} -> {target}")

    # 步骤9：可选地调用原项目解析器和BM25，确认写入后每位英雄确实能被检索。
    kb_checks = {"executed": False}
    if args.repo:
        repo = args.repo.resolve()
        sys.path.insert(0, str(repo))
        from app.kb.guides import load_guides, parse_guide
        from app.kb.index import GuideIndex
        installed = load_guides()
        check(set(installed) == set(heroes), "应用知识库英雄覆盖不符")
        index = GuideIndex(installed)
        for name in heroes:
            path = ROOT / "data/guides" / (name + ".md")
            body = path.read_text(encoding="utf-8")
            guide = parse_guide(body, path)
            check(guide is not None and guide.hero == name, name + "元数据解析失败")
            check((repo / "data/guides" / path.name).read_text(encoding="utf-8") == body, name + "未同步至应用")
            results = index.search(name + " 核心机制 适配流派", hero=name, top_k=3)
            check(bool(results) and all(r["hero"] == name for r in results), name + "知识库检索失败")
        kb_checks = {"executed": True, "guides_loaded": len(installed), "index_chunks": index.n, "heroes_queried": len(heroes)}

    # 步骤10：输出可检查的核验记录；任一失败都会返回非零退出码。
    report = {"status": "PASS" if not failures else "FAIL", "checks": checks,
              "hero_rows_compared": len(hero_rows), "card_rows_compared": len(card_rows),
              "school_count": len(schools), "build_count": len(builds),
              "markdown_files": len(markdown_files), "local_links_checked": link_count,
              "knowledge_base": kb_checks, "failures": failures,
              "limits": ["不证明实战胜率或全版本最优", "未测试真实游戏、桌面置顶和全局快捷键", "未对未知品阶倍率作推定"]}
    output = ROOT / "data/guide_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
