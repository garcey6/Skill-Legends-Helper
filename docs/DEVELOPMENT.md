# 开发与维护

本文面向改代码、跑测试、重建数据的开发者。用户操作见 [USER_GUIDE](USER_GUIDE.md)。
项目基建六件套在仓库根目录：[PRD](../PRD.md)、[RULES](../RULES.md)、
[ARCHITECTURE](../ARCHITECTURE.md)、[DEVELOPMENT_LOG](../DEVELOPMENT_LOG.md)、
[PLAN](../PLAN.md)、[ADR](../ADR.md)；协作入口见 [AGENTS](../AGENTS.md)。

## 本地运行

```powershell
# 只跑网页控制台
python run.py

# 浮窗模式
python agent.py

# 浮窗 + 调试浮层（也可运行时按 Alt+D 开关）
python agent.py --debug

# 不启动网页控制台
python agent.py --no-server

# M1 单图回放（不启动浮窗/控制台）
python -m app --replay tests/fixtures/screenshots/draft001_1800x1118.png

# 从截图生成 fixture 草稿期望，修正标签后再提交
python -m app --generate-expected D:\captures\draft_005.png --out tests/fixtures/expected

# 自动识别层：回放离线帧目录
python -m tools.live_recognize --replay samples/frames/draft_001 --pretty

# 自动识别层：直接抓活窗口（需要标题匹配的游戏窗口）
python -m tools.live_recognize --live --pretty

# 录一段真实帧序列（需要游戏窗口）
python tools/record_frames.py --out samples/frames/draft_004 --frames 30

# 把真实截图登记进 holdout（标签用正式名或别名）
python -X utf8 tools/import_validation.py --image D:\captures\holdout_001.png `
  --name holdout_001 --heroes "森林游侠,神秘法师,魔镜" --note "2560x1600 无边框"
```

## 测试

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # pytest 只用于开发/CI
python -m pytest -q
python tools/validate_cases.py --strict
python tools/run_accuracy.py --strict --min-cases 2
python tools/run_accuracy.py --meta samples/validation/holdout/meta.json --strict --min-cases 8
```

pytest 每次尾部打印 `holdout 用例数：N / 目标 10，缺口 N`；fixture 阈值只升不降。
当前 pytest **146 项通过、3 项按环境跳过**（未装 RapidOCR 时）；安装 OCR 后条件用例会变化。
fixtures 的图片与期望标签在 `tests/fixtures/`，现有 10 组；holdout 只保留引用，避免两套标签源。

- 示例截图识别（3 英雄 / 8 启用 / 5 禁用）；
- M1 静态回放：fixtures 自动发现、真实图逐条断言、`python -m app --replay`、
  `--generate-expected`、`CaptureSource`/`StaticFrameSource` 兼容别名；
- 缩放后的识别（1280px 宽）；
- 自动识别层：色度流派 + 白色符文决胜、RapidOCR 英雄名 + 字模兜底、两套回放夹具、run 数不符降级、稳定性/中位数、名牌碎片合并；
- 攻略 frontmatter / 分段 / 60 篇加载；
- 推荐排序、证据归属、核心被 ban 后分数下降、未知英雄兜底；
- 核心卡选择、立绘/技能图标完整性；
- API keep-alive、`/api/overlay/capture` 触发、图鉴 API、素材自检；
- 浮窗状态渲染、快捷键解析，包括 `Alt+C / Alt+X / Alt+D`；
- 调试浮层：DebugFrame 内容、ROI/OCR/模板框坐标空间、失败原因、标注 PNG、用户目录、按需开关；
- 验证集准确率回归：槽位/英雄名准确率、P50/P95 延迟、失败明细；
- 真实帧导入：别名归一、未知/重复标签拒绝、同帧/同标签重复拒绝、原子写入、`--min-cases` 门槛；
- 字模全名兜底：top5 漏字时按完整英雄名逐字模板分数重排，`极寒掌控者` 恢复；特殊名牌仍为 `null`；
- 真实帧 holdout：10 组独立画面（1800×1118 无边框、2153×1179 窗口化、4 张 1080p/1600p 全屏压力样本、4 张 2560×1390 四英雄截图）的识别与 CI 门槛；C 组已入库，并由全名兜底识别“极寒掌控者”；
- 仓库治理：许可证、风险说明、Issue 模板、五个 `.agents/skills` 的前置元数据；
- 项目基建：六件套存在、README 链接、关键契约（预设优先/字段级/非目标、未核验、只读资产与用户数据、Tkinter）。

`tools/run_accuracy.py` 默认读取 `samples/validation/meta.json`，逐张输出期望/实际英雄名与耗时；
`--strict` 在任一案例不一致或验证集为空时返回 1，`--min-cases N` 进一步要求至少 N 组。
CI 对固定验证集跑 `--min-cases 2`、对真实 holdout 跑 `--min-cases 8`，并上传 `accuracy.json` 与
`holdout_accuracy.json`；真实 holdout 的采集、导入和补到 10 组的计划见 [HOLDOUT](HOLDOUT.md)。

## 文件结构

```text
选技助手/
├─ 启动助手.bat              # 唯一入口菜单（浮窗/网页/设置/退出）
├─ PRD.md                    # 产品边界：系统推荐 / 用户预设
├─ RULES.md                  # 开发流程、验证顺序、未核验规则
├─ ARCHITECTURE.md           # 架构、线程、数据与资产契约
├─ DEVELOPMENT_LOG.md        # 根因与正确做法
├─ PLAN.md                   # 四阶段计划与门槛阶梯
├─ ADR.md                    # 架构决策与待决项
├─ AGENTS.md                 # AI/协作者最小入口、八荣八耻
├─ LICENSE                   # MIT
├─ CHANGELOG.md              # 版本变更记录
├─ .agents/skills/           # 五个仓库内 AI 协作技能
├─ .github/                  # CI 与 Issue/PR 模板
├─ agent.py                  # 浮窗主程序：热键 / 截图 / 识别 / 渲染
├─ run.py                    # 网页版入口
├─ app/
│  ├─ overlay/
│  │  ├─ capture.py          # Win32 截图、窗口查找、DPI、悬浮窗样式
│  │  ├─ hotkey.py           # RegisterHotKey 消息循环
│  │  ├─ debug.py            # M2 调试浮层 / 标注 PNG
│  │  └─ hud.py              # Pillow 卡片渲染 + 置顶可拖动窗口
│  ├─ vision/
│  │  ├─ imageops.py
│  │  ├─ recognizer.py        # 旧的手动截图路径
│  │  ├─ blobs.py             # run / 4 连通 / 名牌分组
│  │  ├─ chroma.py            # 归一化色度
│  │  ├─ schools.py           # 13 类色度 + 一对一约束
│  │  ├─ glyphs.py            # 155 字闭集字模（兜底）
│  │  ├─ ocr.py               # RapidOCR 名牌检测/识别/闭集校正
│  │  ├─ runes.py             # 白色符文掩码
│  │  ├─ debugframe.py        # M2 调试帧（只读，按需构建）
│  │  └─ pipeline.py          # ROI -> Result
│  ├─ live/
│  │  ├─ frame.py             # FrameSource / ROI / 状态
│  │  ├─ sources.py           # M1 兼容别名（CaptureSource / StaticFrameSource）
│  │  ├─ win32src.py          # ROI-only GDI 抓帧
│  │  ├─ replaysrc.py         # 回放 / 单图源
│  │  ├─ stability.py         # diff / median / 指针粗检
│  │  └─ sampler.py           # 采集线程 + 识别线程 + 队列
│  ├─ replay.py              # M1 单图回放 / fixtures / 草稿期望
│  ├─ __main__.py            # python -m app --replay
│  ├─ kb/
│  │  ├─ cards.py            # 卡牌加载 + 每英雄核心卡排序
│  │  ├─ guides.py
│  │  ├─ index.py
│  │  └─ recommend.py
│  ├─ server.py              # 控制台 / 图鉴 / 自检 API + 静态文件
│  ├─ llm.py
│  └─ cli.py
├─ data/
│  ├─ schools.json           # 13 流派 + 机制/派系 ID
│  ├─ heroes.json            # 60 英雄 + 面板/天赋/大招/流派
│  ├─ cards.json             # 156 卡牌 + 双流派/稀有度/效果
│  ├─ rules.json             # 属性/经济/流派规则
│  ├─ guides/*.md            # 60 篇攻略
│  ├─ curated_plans.json     # 逐英雄方案与依据
│  ├─ hero_builds.json       # 完整卡池/分品阶顺序
│  ├─ guide_validation.json  # 攻略核验结果
│  ├─ build_audit.json       # 生成审计
│  ├─ sources.json           # 社区/官方来源
│  ├─ meta_stats.example.json
│  ├─ source/                # 原始 xlsx / txt
│  ├─ art/                   # 60 立绘 + 120 技能图标（仅显示）
│  ├─ templates/             # 旧头像模板 + 流派图标
│  └─ recognize/             # layout / schools_chroma / glyphs
├─ static/
│  ├─ index.html / app.js / styles.css
│  └─ library.html / library.js / library.css
├─ samples/
│  ├─ draft_001.png / window_draft.png
│  ├─ frames/draft_001 / draft_002   # 回放夹具
│  └─ validation/            # 两套真实窗口验证图 + meta.json
│     └─ holdout/            # 真实帧 holdout（由 import_validation.py 登记）
├─ tests/
│  ├─ conftest.py            # pytest 输出 fixture 数/缺口
│  └─ fixtures/
│     ├─ screenshots/        # M1 真实图（两条旧 holdout 已迁入）
│     └─ expected/           # 同名 JSON 期望标签
├─ tools/
│  ├─ preview_draft.py       # 全屏示例
│  ├─ import_game_data.py    # Excel/规则 → JSON
│  ├─ import_art_assets.py   # 立绘/技能图标 → data/art
│  ├─ build_guides.py        # 生成 60 篇攻略
│  ├─ verify_guides.py       # 原表/链接/知识库核验
│  ├─ build_templates.py     # 旧头像模板
│  ├─ build_school_templates.py  # 13 流派色度
│  ├─ build_glyph_templates.py   # 155 字字模
│  ├─ build_school_runes.py      # 13 白色符文模板
│  ├─ seed_glyphs_from_samples.py # 真实字模样例
│  ├─ record_frames.py       # 录真实回放帧
│  ├─ calibrate_thresholds.py    # margin 分布
│  ├─ validate_cases.py      # 两套验证图逐槽位检查
│  ├─ run_accuracy.py        # 槽位/名字准确率与 P50/P95
│  ├─ import_validation.py   # 真实截图登记进验证/holdout
│  ├─ build_release.py       # one-folder PyInstaller 发行包
│  └─ live_recognize.py      # 自动识别 CLI
├─ docs/
├─ tests/
└─ requirements.txt
```

## 重建数据

### 英雄 / 卡牌 / 规则

```powershell
python tools/import_game_data.py
```

需要 `openpyxl`。会读取 `data/source/` 下的 Excel 和规则文本，更新 `heroes.json / cards.json / schools.json / rules.json`，并保留已有头像模板、攻略和别名。

### 攻略知识库

```powershell
python -X utf8 tools/build_guides.py
python -X utf8 tools/verify_guides.py
```

- `build_guides.py` 生成 60 篇攻略、流派目录、导航和审计记录；会覆盖它负责的 Markdown/JSON，手工修改前先备份。
- `verify_guides.py` 核对 Excel 与 JSON、14/3/1 候选池、相对链接和检索，需要 `openpyxl`；结果写入 `data/guide_validation.json`。
- 细节见 [攻略知识库维护说明](攻略知识库维护README.md)。

### 英雄立绘 / 技能图标

```powershell
python tools/import_art_assets.py --source "C:\Users\garcey\Desktop\选技图片素材"
```

源目录包含 `英雄头像/天赋图片/大招图片`。脚本会：

- 立绘转成 300×300 PNG；
- 天赋/大招去掉浅黄底，归一化为 128×128 透明 PNG；
- 处理「渣克鼠王 / 炼金术师 / 月影猎手」三处拼写差异；
- 写入 `heroes.json` 的 `art / talent_icon / ultimate_icon`。

### 识别模板（自动层）

```powershell
# 13 流派色度（面板图标 + 内置示例帧的底部书包变体）
python tools/build_school_templates.py

# 155 字字模（Windows CJK 字体 6 个变体；OCR 兜底）
python tools/build_glyph_templates.py

# 13 白色符文模板（流派 A 决胜）
python tools/build_school_runes.py

# 从内置示例帧补真实字模（神秘法师/守财奴等）
python tools/seed_glyphs_from_samples.py

# 看当前回放的 margin 分布
python tools/calibrate_thresholds.py --replay samples/frames/draft_002

# 重建旧的 3 头像模板（只给网页/--no-auto 用）
python tools/build_templates.py
```

自动层的模板和阈值只在 `data/recognize/`；`data/templates/` 只服务旧路径。

## 运行时文件

以下都是用户数据，不提交；当前仍在程序目录的 `data/` 下，后续按
[ARCHITECTURE](../ARCHITECTURE.md) 的计划迁移到 `%APPDATA%`。

- `data/settings.json`：保存网页设置后生成，可能包含 AI Key，已被 git 忽略。
- `data/captures/last.png`：最近一次手动截图。
- `data/uploads/`：网页控制台上传的截图。
- `data/server_url.txt`：网页控制台实际地址。
- `data/overlay_position.json`：浮窗位置。
- `data/guides/*.md`：60 篇攻略；网页控制台可编辑。**已知债务**：随包目录可能不可写，
  安装到 `Program Files` 时请用免安装目录，或等待后续用户攻略覆盖层。

## 发行包

```powershell
python -m pip install -r requirements-build.txt
python -X utf8 tools/build_release.py --dry-run   # 先看会打包哪些文件
python -X utf8 tools/build_release.py
```

产物在 `dist/`，包含 one-folder 程序、`release.json`、zip 和 SHA256。`PyInstaller` 只放在
`requirements-build.txt`，不要加进运行时依赖。细节和验收步骤见 [RELEASE](RELEASE.md)。

## 版本与提交

```powershell
git status
git diff --stat
git add .
git commit -m "说明"
git push
```

数据文件很大时，先确认 `git diff --stat` 没有误改生成物。`data/source/`、`data/art/` 和 60 篇攻略需要一起提交，否则别人克隆后图鉴或攻略会缺内容。
