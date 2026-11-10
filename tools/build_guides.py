"""按步骤生成60位英雄攻略和13流派卡池；仅使用Python标准库。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

# 步骤1：固定资料版本与目录，避免把网络讨论日期当成游戏数据版本。
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data"
SOURCE_FILES = {
    name: SNAPSHOT / name for name in ("heroes.json", "cards.json", "schools.json", "rules.json")
}
SOURCE_FILES.update({
    name: SNAPSHOT / "source" / name
    for name in ("游戏规则.txt", "卡牌库.xlsx", "选技英雄数据.xlsx")
})
AS_OF = "2026-11-09"
COMMIT = "2922416928acb75c3059f9aae677d81ea63bfd6b"
REPO = "https://github.com/garcey6/Skill-Legends-Helper"
RARITIES = {1: "普通", 2: "稀有", 3: "传奇（数据库称传说）"}
FOUNDATIONS = {104, 119, 137, 153, 167, 181, 194, 206, 217, 227, 236, 244, 251}
COUNTERS = {105, 128, 144, 173, 186, 197, 209, 219, 228, 237, 245, 252}
RARE_ORDER = {
    "basic": [115, 117, 116], "dodge": [132, 134, 133], "crit": [149, 150, 148],
    "life": [163, 165, 164], "heal": [179, 177, 178], "ultimate": [190, 192, 191],
    "poison": [203, 204, 202], "freeze": [214, 213, 215], "shield": [224, 225, 223],
    "vulnerable": [232, 233, 234], "spirit": [242, 240, 241],
    "rage": [249, 248, 247], "haste": [255, 253, 254],
}

# 步骤2：保存逐牌用途，排序依据是触发条件和本英雄收益，而不是稀有度分数。
NOTES = {
    101: "普攻次数越多，获得治疗的机会越多；不是每次必回。",
    102: "需要实际普攻事件；用于补施毒来源。", 103: "适合普攻频繁且需要大招的英雄。",
    104: "增加普攻面板；有攻击系数或攻击分享时收益更明确。",
    105: "只针对敌方普通攻击，不能阻止全部物理技能。",
    106: "普攻挂冰；未命中等结算细节仍看客户端。", 107: "普攻提供护盾机会，先有普攻频率。",
    108: "收益取决于不同普攻技能种类；同名升级不增加种类。",
    109: "普攻提供易伤来源，适合后续多次伤害。", 110: "先有闪避事件；短时攻击增益有叠加上限。",
    111: "先有暴击事件；短时攻击增益有叠加上限。", 112: "只强化第一个精灵，攻击力越高越有价值。",
    113: "只在狂怒期间增加攻击，未进入狂怒前不提供收益。",
    114: "普攻转急速；{val4}含义未被源表定义。", 115: "需要时间叠攻速；魔镜不依赖常规攻速普攻。",
    116: "周期魔法伤害，读取攻击力差；模板系数须核实。", 117: "开局5秒攻击增益，适合短战斗或攻击系数技能。",
    118: "普通攻击连击；不能把非普攻物理技能当成普攻。", 119: "提升物理闪避概率，默认不解决中毒和魔法伤害。",
    120: "成功闪避后挂毒；对非物理为主的对手触发可能不足。",
    121: "成功闪避后挂冰；先看敌人是否提供可闪避伤害。",
    122: "闪避后概率回能；不能用面板闪避数直接当回能次数。",
    123: "闪避回血，适合持续承受物理攻击。", 124: "闪避后得盾，防御收益依赖触发频率。",
    125: "闪避挂易伤；还需要伤害来源消耗易伤。", 126: "按不同闪避技能种类增加生命。",
    127: "周期物理伤害读取闪避加暴击；不是普通攻击。", 128: "对高闪避对手提高有效命中，不能直接当成必中。",
    129: "闪避点数转第一只精灵最大生命。", 130: "狂怒期间临时增加闪避，先建立怒气。",
    131: "成功闪避后获得急速，循环路线的条件组件。", 132: "魔法闪避概率由卡牌单独给出，不能直接套物理闪避率。",
    133: "开局5秒闪避增益，偏防首轮物理爆发。", 134: "闪避后的反击有概率，但反击本身标明不可闪避。",
    135: "先成功闪避再概率反射，反射造成魔法伤害。", 136: "暴击产生治疗，先有可暴击伤害和概率。",
    137: "增加暴击点数；不提高觅血蛛王固定的毒暴击概率。", 138: "暴击挂毒；特殊毒暴击能否继续触发需核实。",
    139: "暴击挂冰，适合冰层与暴击有联动的英雄。", 140: "暴击后概率回能；暴击频率越高越有机会。",
    141: "暴击获得护盾，连接物理输出和盾触发。", 142: "暴击挂易伤；适合后续伤害能快速利用层数的局。",
    143: "按不同暴击技能种类增加生命。", 144: "针对敌方暴击；不是一般伤害减免。",
    145: "暴击点数转第一只精灵生命。", 146: "狂怒期间增加暴击，未狂怒前无此增益。",
    147: "暴击获得急速，是暴击周期循环路线的桥接牌。", 148: "为魔法伤害单独提供暴击概率，不能视为物理暴击率全量继承。",
    149: "每次暴击附加按敌人当前生命计算的伤害；频率与命中重要。", 150: "开局5秒提高暴击，适合首轮物理爆发。",
    151: "开局神圣伤害并削最大生命；不按普通物理暴伤再次放大。", 152: "按已损失生命周期回复，残血才有明显收益。",
    153: "提高承伤空间；生命系数英雄还有输出收益。", 154: "按自身已损失生命挂毒，满血收益很低。",
    155: "按已损失生命挂冰，属于受损后启动。", 156: "按已损失生命挂易伤，需要先承伤。",
    157: "高最大生命才体现回能增益，且模板有上限。", 158: "开局按敌人最大生命偷取，模板上限须核实。",
    159: "按已损失生命周期得盾，不是开局厚盾。", 160: "自身最大生命转第一只精灵生命。",
    161: "已损失生命转怒气；不能为启动而盲目压低血量。", 162: "受损后周期得急速，先保证活过启动。",
    163: "周期物理伤害读取自身最大生命，厚血路线的输出点。", 164: "按已损失生命提高非神圣伤害，残血也更危险。",
    165: "针对魔法伤害，不能减少全部伤害类型。", 166: "首次死亡复活并清除负面，偏容错与第二次输出机会。",
    167: "独立稳定的周期治疗源，能启动多种治疗触发牌。", 168: "治疗时概率挂冰，先有回复事件。",
    169: "治疗时概率挂毒，先有回复事件。", 170: "治疗时概率得盾，转盾英雄还需核实触发顺序。",
    171: "按在场精灵数量治疗英雄，不是治疗精灵。", 172: "释放大招后治疗，适合高大招频率。",
    173: "针对敌方回复，不是直接减少敌方最大生命。", 174: "治疗时概率施加易伤，先有治疗源。",
    175: "按治疗量获得怒气，重视实际治疗量。", 176: "治疗时概率得急速，先有足够治疗事件。",
    177: "治疗触发魔法射线，回复频率是主要条件。", 178: "周期物理伤害读取期间累计治疗量，区别于治疗次数。",
    179: "伤害事件有概率治疗，需要稳定输出频率。", 180: "首次低于30%生命才触发，不能当开局常驻回复。",
    181: "独立周期回能，直接改善大招启动。", 182: "大招得盾，连接回能与护盾触发。",
    183: "大招挂毒，先解决能量启动。", 184: "大招挂冰，适合冰层和回能联动。",
    185: "大招挂易伤；基础15层不满足骸骨鸦医的大于16层阈值。", 186: "压低敌人回能，优先针对大招依赖对手。",
    187: "要求精灵在场；具体哪些大招数值可增幅不能一概而论。", 188: "狂怒窗口内回能，怒气不足时收益有限。",
    189: "施放大招后得急速，帮助周期组件。", 190: "大招后短时间密集回能，需要先放出第一发。",
    191: "大招附眩晕，数据库注明其间无法普攻、闪避、释放大招。", 192: "伤害事件概率回能，多段伤害更有机会。",
    193: "开局大招启动；仅该次效果提高30%，不代表全部后续大招增幅。", 194: "独立周期挂毒，低依赖启动。",
    195: "获得护盾时仅5%概率挂毒，需要得盾频率。", 196: "施加易伤时仅5%概率挂毒，需要施加易伤来源。",
    197: "降低受到的中毒伤害；不是清除全部中毒层数。", 198: "提高已有毒伤，必须同时有敌人冰层和毒伤来源。",
    199: "精灵数量决定周期施毒量，先保证精灵在场。", 200: "狂怒期间按怒气挂毒，受状态窗口限制。",
    201: "急速加快毒结算，需要足够急速与毒来源。", 202: "受击概率挂毒，偏反打而非纯开局爆发。",
    203: "开局挂毒，配开局易伤可抢早期伤害。", 204: "非中毒伤害概率产生毒伤，不是所有毒伤都继续触发。",
    205: "首次半血挂毒并额外结算，需先活到触发点。", 206: "独立周期挂冰，冰冻路线的稳定来源。",
    207: "获得护盾时低概率挂冰，需要得盾频率。", 208: "施加易伤时低概率挂冰，需要易伤来源。",
    209: "降低对方施加冰冻的效率，针对冰层压制。", 210: "按在场精灵数量周期挂冰。",
    211: "狂怒期间按怒气挂冰，不能视作常驻。", 212: "需敌人有冰层且自己正在获得急速。",
    213: "开局冰层，适合立即利用冰层的英雄或卡牌。", 214: "施加冰冻概率造成魔法伤害，侧重挂冰事件频率。",
    215: "受击概率挂冰，偏承伤反打。", 216: "周期魔法伤害读取冰层；循环体系需检查最高效能目标。",
    217: "独立周期得盾，能启动得盾触发牌。", 218: "高频魔法伤害读取两类技能种类；双流派归属去重与公式计数分开。",
    219: "降低对方获得护盾效率，针对高产盾对手。", 220: "按在场精灵数量周期得盾。",
    221: "按护盾实际挡伤获得怒气，不能按获得盾量计算。", 222: "得盾时低概率得急速，先有频繁得盾来源。",
    223: "提供开局盾量，偏防首轮爆发。", 224: "按不同盾技能种类降低每次非神圣伤害，对多段攻击更有针对性。",
    225: "得盾概率产生物理盾牌，侧重得盾次数。", 226: "首次即将死亡时大量得盾，仍须注意神圣伤害。",
    227: "独立周期施加易伤，低依赖启动。", 228: "降低对方施加易伤效率，不等于完全免疫。",
    229: "按精灵数周期挂易伤，要求精灵存活。", 230: "狂怒期间按怒气施加易伤。",
    231: "施加易伤时低概率得急速，需要足够施加频率。", 232: "开局易伤，需有即时伤害跟进。",
    233: "不同易伤技能种类增加每次非神圣伤害，多段输出更合适。", 234: "易伤量随战斗时间增长，短战斗收益小。",
    235: "高频挂易伤加魔法伤害，注意周期循环目标竞争。", 236: "只增加第一个精灵的最大生命，不直接增加数量。",
    237: "针对敌方精灵最大生命，不等于立即消灭精灵。", 238: "精灵阵亡才给怒气，依赖死亡事件。",
    239: "精灵阵亡才给急速，依赖死亡事件。", 240: "首次半血陆续召唤精灵，防御兼数量增益。",
    241: "精灵阵亡后造成魔法伤害；活着的精灵不会持续殉葬。", 242: "每只精灵周期输出物理弹珠，精灵数量与存活重要。",
    243: "开局额外精灵生命取第一只的40%，提升数量型掌控牌收益。", 244: "敌人伤害行为产生怒气，频率不足时启动较慢。",
    245: "降低敌人怒气获取，针对狂怒依赖对手。", 246: "进入狂怒时得急速，需先完成怒气启动。",
    247: "狂怒期间周期魔法伤害，模板系数未被源表单独定义。", 248: "狂怒期间减伤，非全程减伤。",
    249: "延长狂怒，提升只在狂怒中生效的组件覆盖。", 250: "狂怒中用怒气抵消致死伤害；受状态和剩余怒气限制。",
    251: "独立周期急速来源，先建立有用的周期技能。", 252: "降低敌人获得急速效率，针对周期流。",
    253: "开局急速，适合短战斗启动。", 254: "需累计10次周期生效才发导弹，不是拿到即输出。",
    255: "获得急速概率触发最高效能周期技能；目标选择细则未收录。", 256: "周期神圣伤害；可能改变周期循环的目标，不能一律视作升级。",
}


def read_json(path: Path):
    """步骤3：统一按UTF-8读取，保留中文名字与原始数值。"""
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str):
    """步骤4：只写目标包内生成文件；不改原始数据库。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def effect(card):
    """步骤5：只替换定义明确的{val}；{valN}留原样并提示待核实。"""
    base = card.get("base_value")
    value = f"{base:g}" if isinstance(base, (float, int)) else "未提供"
    text = card["desc_template"].replace("{val}", value)
    return text + ("〔含未定义倍率占位符〕" if re.search(r"\{val\d+\}", text) else "")


def rank_card(card, plan, sid):
    """步骤6：先处理机制例外，再按关键卡、同系补强、条件牌、反制牌排序。"""
    cid = card["id"]
    if plan["hero"] == "魔镜" and cid == 115:
        return (4, 0, "暂缓", "不以常规攻速触发普攻，此路线不优先投资精神振奋。")
    if plan["hero"] in {"森林游侠", "星涡语者"} and cid == 256:
        return (4, 0, "先核实", "可能把周期循环目标从英雄技能转走；确认转换路线后再拿。")
    if cid in plan["focus"]:
        return (0, plan["focus"].index(cid), "P0 核心", NOTES[cid])
    if cid in COUNTERS:
        return (3, cid, "对局反制", NOTES[cid])
    if card["rarity"] == 2:
        return (1, RARE_ORDER[sid].index(cid), "P1 补强", NOTES[cid])
    if card["rarity"] == 3:
        return (1, cid, "P1 终局候选", NOTES[cid])
    if cid in FOUNDATIONS or set(plan["schools"]).issubset(card["faction_ids"]):
        return (1, cid, "P1 补强", NOTES[cid])
    return (2, cid, "P2 条件补牌", NOTES[cid])


def table_for(cards, plan, sid, rarity):
    """步骤7：按流派成员关系提取完整卡池，不能只取primary_faction。"""
    selected = [c for c in cards if sid in c["faction_ids"] and c["rarity"] == rarity]
    selected.sort(key=lambda c: rank_card(c, plan, sid)[:2])
    lines = ["|顺序|卡牌ID与名称|优先级|基础值|归属|基础效果与选取理由|", "|---|---|---|---|---|---|"]
    records = []
    for number, card in enumerate(selected, 1):
        _, _, priority, reason = rank_card(card, plan, sid)
        name = f"{card['id']} {card['name']}"
        desc = effect(card).replace("|", "／").replace("\n", " ")
        base = f"{card['base_value']:g}" if card.get("base_value") is not None else "未提供"
        lines.append(f"|{number}|{name}|{priority}|{base}|{'＋'.join(card['factions'])}|{desc} 取牌：{reason}|")
        records.append({"id": card["id"], "priority": priority, "rank_within_rarity": number, "reason": reason})
    return "\n".join(lines), records


def constraints(plan):
    """步骤8：按机制生成对手与禁用条件，避免固定写成必胜克制关系。"""
    s = set(plan["schools"])
    out = []
    if s & {"basic", "crit", "dodge"}:
        out.append("依赖物理命中时观察对手闪避；灵巧枷锁可针对闪避，但本局是否能取得以商店为准。")
    if "heal" in s:
        out.append("敌方治疗干扰会压低回复；若输在第一轮爆发，先补即时生存，不能只加长期治疗。")
    if "shield" in s:
        out.append("易伤会与护盾抵消，神圣伤害绕过护盾减伤；护盾量高不等于不会死亡。")
    if "ultimate" in s:
        out.append("能量损耗和眩晕会影响大招循环；冰冻影响攻速和弹道，不应笼统写成所有冰冻都禁止施法。")
    if "haste" in s:
        out.append("冰冻与急速相互抵消；急速损耗降低产速。补牌时检查周期循环是否仍命中预期技能。")
    if "poison" in s:
        out.append("对手中毒解药降低毒伤；高生命本身不必然怕毒，普通中毒按层数结算而非按最大生命百分比结算。")
    if "spirit" in s:
        out.append("驱逐精灵降低敌方精灵最大生命；数量型掌控牌要求精灵实际存活。")
    return out or ["对照伤害统计寻找短板，再购买对应的防御或反制组件。"]


def build_one(hero, plan, cards, schools, sources):
    """步骤9：输出攻略正文和机器可读的去重卡组，保持hero字段兼容原知识库。"""
    names = [schools[x]["name"] for x in plan["schools"]]
    by_id = {c["id"]: c for c in cards}
    selected_ids = {c["id"] for c in cards if set(c["faction_ids"]) & set(plan["schools"])}
    if any(cid not in selected_ids for cid in plan["focus"]):
        raise ValueError(f"{hero['name']}核心卡不在主副流派池内")
    focus_cards = [by_id[cid] for cid in plan["focus"]]
    stage = {r: [c for c in focus_cards if c["rarity"] == r] for r in (1, 2, 3)}
    sequence = lambda r: " → ".join(c["name"] for c in stage[r]) or "按下表条件选取"
    shared = [c for c in cards if set(plan["schools"]).issubset(c["faction_ids"])]
    text = ["---", f"hero: {hero['name']}", f"title: {hero['name']} {'与'.join(names)}构筑攻略",
            f"schools: {', '.join(names)}", 'patch: "仓库2026.11数据快照"',
            f"source: 仓库技能与卡牌数据；机制推导；注明日期的社区观点", f"updated: {AS_OF}",
            "evidence_status: 机制推导与社区交叉核对，未经实战胜率验证", "---", "",
            f"# {hero['name']}构筑攻略", "", "## 一句话结论", "",
            f"默认候选为{'＋'.join(names)}，先完成核心触发链，再补生存和反制。这里的推荐依据英雄技能，不是全版本胜率榜；前提是本局两系开放，且尚未给出宝物、对手和已有卡。", "",
            "## 核心机制", "", f"- 数据库天赋：{hero['talent']}", f"- 数据库大招：{hero['ultimate']}",
            f"- 机制边界：{plan['caution']}", "", "## 适配流派", ""]
    for role, sid, why in zip(("主系", "副系"), plan["schools"], plan["rationale"]):
        school = schools[sid]
        text.append(f"- {role} {school['name']}（ID {school['faction_id']} / {sid}）：{why}")
    text += ["", "## 开局抓牌顺序", "", f"- 启动阶段：优先寻找{sequence(1)}；只买已能触发或能启动联动的组件。",
             f"- 稀有牌阶段：{sequence(2)}。这是条件优先级，生存告急或遇到克制对手时调整顺序。",
             f"- 终局阶段：{sequence(3)}。传奇出现条件未在本仓库规则中完整定义，不保证固定回合能取得。",
             "- 前期没有关键牌时保留转向空间；先用能生效的普通卡过渡，不为凑满18种而强买低效组件。", "",
             "## 核心卡组与共享牌", "",
             f"两系共享卡：{'、'.join(str(c['id'])+' '+c['name'] for c in shared)}。两份18种候选池合计36条归属，按ID去重为{len(selected_ids)}种卡（普通27、稀有6、传奇2）；不是要求买35张。",
             "普通14、稀有3、传奇1是每个流派的卡种结构。P0表示本方案关键组件，不表示任何经济或血量下都必须购买；稀有和传奇还受商店实际可用性限制。",
             "以下基础效果只替换{val}。{val4}等占位符保留原文，源表没有定义其倍率；基础值为0的传奇仍按固定文字生效。", ""]
    pools = {}
    for sid in plan["schools"]:
        text += [f"## {schools[sid]['name']}完整候选池", ""]
        pools[sid] = {}
        for rarity, count in ((1, 14), (2, 3), (3, 1)):
            table, rows = table_for(cards, plan, sid, rarity)
            text += [f"### {RARITIES[rarity]} {count}种", "", table, ""]
            pools[sid][str(rarity)] = rows
    text += ["## 宝物与技能选择", "",
             "- 核心组件难找时偏向可增加刷新或定向找牌机会的宝物；缺持续资源时再考虑经济。",
             "- 血量不足时优先能让当前构筑活过启动的保命效果，不能把存满利息设为无条件目标。",
             "- 本仓库没有完整宝物数据库，故不编造宝物倍率、组合限制或必选榜；按客户端当前效果核对。", "",
             "## 克制关系", ""] + ["- " + x for x in constraints(plan)]
    text += ["", "## 禁用流派与转型", "",
             f"- {names[0]}被禁：本页主路线不成立，重新按剩余开放流派及英雄技能判断，不能让推荐流派权重代替可获取性。",
             f"- {names[1]}被禁：回到{names[0]}的独立启动组件；共享卡是否仍可出现、是否仍可有效触发，以实际商店为准。",
             "- 双流派归属不等于两张牌；共享卡一侧被禁后的出现条件、双系经验分配和卡池返还细则未被源表定义，不据此自动断言可买或不可买。", "",
             "## 常见失误", "", f"- {plan['caution']}",
             "- 把普通、稀有、传奇的ID 1/2/3当伤害倍率，或把卡池总量15/9/3当个人携带上限。",
             "- 把知识库建议当客户端已验证的胜率；忽略本局开放流派、卡池竞争、宝物与生存压力。", "",
             "## 社区观点与版本核对", ""]
    if plan["community_refs"]:
        for ref in plan["community_refs"]:
            source = sources[ref]
            text.append(f"- [{source['title']}]({source['url']})：{source['date']}，{source['kind']}。用途：{source['use']}。")
    else:
        text += ["本轮未取得可逐项核验、且专门覆盖该英雄当前版本的社区构筑。上面的流派与排序因此标记为机制推导；通用环境讨论和已查到的11月构筑资料见附录，不借其他英雄的讨论给本英雄背书。"]
    text += ["", "当前检索截至2026-11-09。7—8月帖子仅用于构筑思路，不能作为11月强度排名；具体技能数值一律按本次仓库数据。", "",
             "## 数据出处与使用教程", "",
             f"- [固定版本英雄数据]({REPO}/blob/{COMMIT}/data/heroes.json)",
             f"- [固定版本卡牌数据]({REPO}/blob/{COMMIT}/data/cards.json)",
             "- [网站版与浮窗助手版完整教程](../../docs/网站版与浮窗助手版完整教程.md)",
             "- [规则、倍率和双流派核对](../../docs/规则与数据核对.md)",
             "- [社区来源及冲突处理](../../docs/社区来源与版本差异.md)", "",
             "项目图鉴当前用纯文本显示攻略，若相对链接不可点击，请在项目docs目录打开对应文件。",
             "网站与浮窗的短卡片仍由原有评分与选卡代码生成；详细攻略属于独立知识库层，并未自动改写评分权重或那3至6张展示卡。"]
    record = {"hero_id": hero["id"], "hero": hero["name"], "schools": plan["schools"], "focus": plan["focus"],
              "pools": pools, "unique_card_ids": sorted(selected_ids), "shared_card_ids": [c["id"] for c in shared],
              "basis": "mechanistic_inference_with_labeled_community_evidence", "community_refs": plan["community_refs"]}
    return "\n".join(text), record


def install_guides(target: Path):
    """步骤10：可选地写入已有项目；先备份旧攻略，绝不删除目录。"""
    target = target.resolve()
    if not (target / "app/kb/guides.py").is_file() or not (target / "data/heroes.json").is_file():
        raise ValueError("目标不是Skill-Legends-Helper项目根目录")
    destination = target / "data/guides"
    destination.mkdir(parents=True, exist_ok=True)
    backup = target / "data/guide_backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup.mkdir(parents=True)
    for source in (ROOT / "data/guides").glob("*.md"):
        dest = destination / source.name
        if dest.exists():
            shutil.copy2(dest, backup / dest.name)
        shutil.copy2(source, dest)
    # 步骤10.1：同步攻略引用的说明文档，保证相对链接在目标项目内仍有效。
    for source in (ROOT / "docs").rglob("*.md"):
        relative = source.relative_to(ROOT)
        dest = target / relative
        if dest.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    return str(backup)


def main():
    # 步骤11：加载输入并检查唯一ID、每流派数量和人工计划覆盖，失败时中止写入。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-to", type=Path, help="可选：备份并更新指定项目的攻略目录")
    args = parser.parse_args()
    hero_data = read_json(SNAPSHOT / "heroes.json")
    card_data = read_json(SNAPSHOT / "cards.json")
    school_data = read_json(SNAPSHOT / "schools.json")
    plans = read_json(ROOT / "data/curated_plans.json")["plans"]
    sources = {x["id"]: x for x in read_json(ROOT / "data/sources.json")["sources"]}
    heroes, cards = hero_data["heroes"], card_data["cards"]
    schools = {s["id"]: s for s in school_data["schools"]}
    by_plan = {p["hero"]: p for p in plans}
    assert len(heroes) == len(by_plan) == 60
    assert {h["name"] for h in heroes} == set(by_plan)
    assert len(cards) == len({c["id"] for c in cards}) == 156
    assert set(NOTES) == {c["id"] for c in cards}
    for sid in schools:
        assert Counter(c["rarity"] for c in cards if sid in c["faction_ids"]) == {1: 14, 2: 3, 3: 1}
    for p in plans:
        assert len(p["schools"]) == len(set(p["schools"])) == 2
        assert set(p["schools"]) <= set(schools)
        assert len(p["rationale"]) == 2 and len(p["focus"]) == len(set(p["focus"]))
        assert all(x in sources for x in p["community_refs"])

    # 步骤12：生成60篇兼容知识库的攻略、去重卡组和全英雄导航。
    builds = []
    index = ["# 全英雄构筑速查", "", "60位英雄均来自指定仓库。每位给出一组主副流派候选及完整卡池；机制推导不等于实战最优。鬼牌的路线须先满足复制对象条件。", "",
             "|英雄|默认主系|默认副系|第一批普通组件|", "|---|---|---|---|"]
    by_id = {c["id"]: c for c in cards}
    for hero in heroes:
        p = by_plan[hero["name"]]
        body, record = build_one(hero, p, cards, schools, sources)
        write_text(ROOT / "data/guides" / (hero["name"] + ".md"), body)
        builds.append(record)
        core = "、".join(by_id[cid]["name"] for cid in p["focus"] if by_id[cid]["rarity"] == 1)
        index.append(f"|[{hero['name']}](../data/guides/{hero['name']}.md)|{schools[p['schools'][0]]['name']}|{schools[p['schools'][1]]['name']}|{core}|")
    write_text(ROOT / "docs/全英雄构筑速查.md", "\n".join(index))
    write_text(ROOT / "data/hero_builds.json", json.dumps({"as_of": AS_OF, "builds": builds}, ensure_ascii=False, indent=2))

    # 步骤13：导出13个不带英雄偏好的候选池，保留基础值和原始模板以便核查。
    for sid, school in schools.items():
        lines = [f"# {school['name']}卡池", "", f"流派ID：{school['faction_id']}；程序ID：{sid}。", "",
                 "14种普通、3种稀有、1种传奇。下面是数据目录，不表示必须买齐；英雄优先级见对应攻略。", ""]
        for rarity in (1, 2, 3):
            lines += [f"## {RARITIES[rarity]}", "", "|卡牌ID|名称|基础值|卡池总量|流派归属|原始效果模板|", "|---|---|---|---|---|---|"]
            for c in cards:
                if sid in c["faction_ids"] and c["rarity"] == rarity:
                    lines.append(f"|{c['id']}|{c['name']}|{c['base_value']:g}|{c['pool']}|{'＋'.join(c['factions'])}|{c['desc_template']}|")
            lines.append("")
        write_text(ROOT / "docs/流派卡池" / (school["name"] + ".md"), "\n".join(lines))

    # 步骤14：记录来源哈希和统计，不把未知倍率或示例排名包装为已验证事实。
    audit = {"as_of": AS_OF, "repository": REPO, "commit": COMMIT,
             "hero_count": len(heroes), "unique_cards": len(cards), "school_count": len(schools),
             "rarities": dict(Counter(c["rarity_name"] for c in cards)),
             "dual_school_cards": sum(len(c["faction_ids"]) == 2 for c in cards),
             "memberships": sum(len(c["faction_ids"]) for c in cards),
             "undefined_template_cards": [c["id"] for c in cards if re.search(r"\{val\d+\}", c["desc_template"])],
             "grade_multipliers": "not_provided_not_inferred", "guide_count": len(builds),
             "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE_FILES.values()},
             "gameplay_testing": "not_run", "score_model_changed": False}
    if args.install_to:
        audit["guide_backup"] = install_guides(args.install_to)
    write_text(ROOT / "data/build_audit.json", json.dumps(audit, ensure_ascii=False, indent=2))
    print(json.dumps({k: audit[k] for k in ("guide_count", "hero_count", "unique_cards", "school_count", "dual_school_cards", "memberships")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
