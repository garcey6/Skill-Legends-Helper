# 开发与维护

本文面向改代码、跑测试、重建数据的开发者。用户操作见 [USER_GUIDE](USER_GUIDE.md)。

## 本地运行

```powershell
# 只跑网页控制台
python run.py

# 浮窗模式
python agent.py

# 不启动网页控制台
python agent.py --no-server

# 命令行分析一张截图
python -m app.cli samples/draft_001.png

# 自动识别层：回放离线帧
python -m tools.live_recognize --replay samples/frames/draft_001 --pretty

# 自动识别层：直接抓活窗口（需要标题匹配的游戏窗口）
python -m tools.live_recognize --live --pretty

# 录一段真实帧序列（需要游戏窗口）
python tools/record_frames.py --out samples/frames/draft_004 --frames 30
```

## 测试

```powershell
python -m unittest discover -s tests -t . -v
```

当前共 **43 项**，覆盖：

- 示例截图识别（3 英雄 / 8 启用 / 5 禁用）；
- 缩放后的识别（1280px 宽）；
- 自动识别层：色度流派 + 白色符文决胜、RapidOCR 英雄名 + 字模兜底、两套回放夹具、run 数不符降级、稳定性/中位数；
- 攻略 frontmatter / 分段 / 60 篇加载；
- 推荐排序、证据归属、核心被 ban 后分数下降、未知英雄兜底；
- 核心卡选择、立绘/技能图标完整性；
- API keep-alive、`/api/overlay/capture` 触发、图鉴 API、素材自检；
- 浮窗状态渲染、快捷键解析，包括 `Alt+C / Alt+X`。

## 文件结构

```text
选技助手/
├─ 启动助手.bat              # 启动浮窗（= 启动浮窗.bat）
├─ 启动浮窗.bat              # 浮窗主启动器
├─ 启动网页版.bat            # 只启动网页控制台
├─ 打开设置.bat              # 打开实际端口的网页控制台
├─ agent.py                  # 浮窗主程序：热键 / 截图 / 识别 / 渲染
├─ run.py                    # 网页版入口
├─ app/
│  ├─ overlay/
│  │  ├─ capture.py          # Win32 截图、窗口查找、DPI、悬浮窗样式
│  │  ├─ hotkey.py           # RegisterHotKey 消息循环
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
│  │  └─ pipeline.py          # ROI -> Result
│  ├─ live/
│  │  ├─ frame.py             # FrameSource / ROI / 状态
│  │  ├─ win32src.py          # ROI-only GDI 抓帧
│  │  ├─ replaysrc.py         # 回放 / 单图源
│  │  ├─ stability.py         # diff / median / 指针粗检
│  │  └─ sampler.py           # 采集线程 + 识别线程 + 队列
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
│  └─ frames/draft_001 / draft_002   # 回放夹具
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

- `data/settings.json`：保存网页设置后生成，可能包含 AI Key，已被 git 忽略。
- `data/captures/last.png`：最近一次截图。
- `data/server_url.txt`：网页控制台实际地址。
- `data/overlay_position.json`：浮窗位置。

## 版本与提交

```powershell
git status
git diff --stat
git add .
git commit -m "说明"
git push
```

数据文件很大时，先确认 `git diff --stat` 没有误改生成物。`data/source/`、`data/art/` 和 60 篇攻略需要一起提交，否则别人克隆后图鉴或攻略会缺内容。
