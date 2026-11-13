# 数据来源与致谢

本文说明数据表、图片素材、攻略知识库和公开来源。使用方式见 [USER_GUIDE](USER_GUIDE.md)，评分逻辑见 [SCORING_AND_RAG](SCORING_AND_RAG.md)。

## 你提供的数据

| 原始文件 | 内容 | 入库位置 |
| --- | --- | --- |
| `选技英雄数据.xlsx` | 60 英雄：生命 / 攻击 / 攻速 / 回能 / 闪避 / 暴击 / 天赋 / 大招 | `data/heroes.json` |
| `卡牌库.xlsx` | 156 卡牌：名称 / 稀有度 / 双流派 / 卡池数量 / 基础值 / 效果模板；13 流派 ID 表 | `data/cards.json` |
| `游戏规则.txt` | 基础属性、经济 / 利息、13 流派机制 | `data/rules.json`、`data/schools.json` |
| `选技图片素材/` | 60 张 300×300 英雄立绘、60 张天赋图标、60 张大招图标 | `data/art/` |

原始文件复制在 `data/source/`。`tools/import_game_data.py` 可重复导入英雄、卡牌和规则；`tools/import_art_assets.py` 可重复导入图片。

## 图片素材

- 英雄立绘：300×300，存入 `data/art/heroes/<hero_id>.png`，只用于浮窗、结果卡和图鉴显示。
- 天赋 / 大招图标：源图约 125×125 / 114×115，去掉浅黄底后归一化为 128×128 透明 PNG，存入 `data/art/skills/`。
- 三处源文件拼写差异已加别名：
  - 渣克鼠王 → 渣客鼠王
  - 炼金术师 → 炼金术士
  - 月影猎手 → 月隐猎手
- **展示立绘不参与自动识别**。自动识别读 `data/recognize/glyphs.json` 的 16×16 汉字字模；旧的手动路径仍读 `data/templates/heroes/` 的 147×224 头像（3 个）。

## 识别模板

- `data/recognize/schools_chroma.json`：13 流派归一化色度。基础模板来自 `data/templates/schools/*.png` 的 13 个面板图标；每类 1~3 个变体，变体来自 `samples/draft_001.png` 和 `samples/window_draft.png` 的底部书包。`life` / `vulnerable` 目前只有基础模板，没有干净底部变体。
- `data/recognize/glyphs.json`：60 个英雄名用到的 **155 个不同汉字**，共 **951** 个 16×16 字模向量：
  - 930 个来自 Windows 自带 6 个字体的渲染：SimHei、SimSun、Microsoft YaHei、Microsoft YaHei Bold、DengXian Bold、STXiHei；64px 渲染、裁 bbox、缩放 16×16、减均值除标准差。
  - 21 个（20 个不同字）来自两段示例帧真实切字：`samples/draft_001.png`（森林游侠/神秘法师/魔镜）和 `samples/window_draft.png`（守财奴/狂暴战将/精灵牧师）。
  - **没有游戏原字体**；`coverage=1.0` 只表示 155 字都有字体模板，不等于游戏字体完全一致。
- `data/recognize/layout.json`：两个 ROI、期望启用数、margin、稳定门和字模阈值。
- `samples/frames/draft_001` / `draft_002`：离线回放夹具，用于无游戏回归。
- `samples/validation/`：2026-11-13 新增的两张真实窗口验证帧，**只验证，不参与模板生成**；当前结果见该目录 README。

## 攻略知识库

`data/guides/` 内置 60 篇英雄构筑攻略，配套数据：

- `data/curated_plans.json`：逐英雄方案、判定依据、核心卡、例外和来源引用；
- `data/hero_builds.json`：完整卡池、分品阶顺序和共享卡去重结果；
- `data/sources.json`：社区/官方链接、日期、用途和版本限制；
- `data/build_audit.json`：生成时的资料哈希、数量和证据边界；
- `data/guide_validation.json`：最近一次原表、文档和检索核验结果。

维护与核验方式见 [攻略知识库维护说明](攻略知识库维护README.md)、[规则与数据核对](规则与数据核对.md)、[社区来源与版本差异](社区来源与版本差异.md)。

## 数据口径

- 英雄 `power/tier` 不是官方胜率：匹配英雄保留初始整理值，其余按基础面板估算；图鉴顶部会标注「不是官方胜率」。
- 卡牌表只提供 `base_val_1`。`{val}` 用基础值，`{valN}` 按基础值 × N 渲染；实际以游戏内卡牌等级为准。
- 双流派按卡牌 ID 去重；每个流派 18 张候选卡（普通 14、稀有 3、传奇 1）是候选池结构，不表示必须买满。
- 构筑攻略尚未经实战胜率验证，应结合本局开放流派、已有牌、宝物和对手调整。

## 公开攻略与致谢

流派机制、英雄定位和部分玩法结论整理自公开攻略：

- [游侠网《选技大乱斗》流派推荐](https://gl.ali213.net/html/2024-9/1496457.html)
- [TapTap 新人角色推荐](https://www.taptap.cn/moment/823256288749160452)
- [九游 神秘法师攻略](https://a.9game.cn/xuanjidaluandou/11984418.html)
- [Steam 2026-07-01 更新公告（魔镜 / 疾影剑卫）](https://store.steampowered.com/news/app/3114410/view/699894448411118033)
- [TapTap 守财奴攻略](https://www.taptap.cn/moment/819755514698140923)

本项目是非官方的个人辅助工具，与游戏开发商无关。英雄强度、流派契合度和评分是整理后的示例数据，请以你自己的对局体验为准。
