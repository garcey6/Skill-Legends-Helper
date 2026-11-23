# ARCHITECTURE.md

> 运行架构、模块边界与数据/资产契约。本文描述**当前仓库实际实现**；标“计划”的部分尚未
> 落地，不得当成已有能力。产品需求见 [PRD](PRD.md)，决策记录见 [ADR](ADR.md)。

## 1. 系统上下文

```text
┌──────────────────────────── Windows 桌面 ────────────────────────────┐
│  游戏窗口（无边框/窗口化）                                           │
│      │ 客户区像素（只读）                                           │
│      ▼                                                              │
│  WindowFrameSource ──► LiveSampler ──► 识别管线 ──► Advisor         │
│      │                    │                    │          │         │
│      │                    └─ 采集/识别线程      │          ▼         │
│      │                                         │     Tkinter 浮窗   │
│      └─────────────────────────────────────────┴──►  Pillow 卡片    │
│                                                                     │
│  StaticFrameSource ──► app.replay ──► 识别管线                       │
│  run.py ──► 本地 HTTP 控制台（HTML/JS）──► 攻略/设置/图鉴/上传       │
└─────────────────────────────────────────────────────────────────────┘
```

- 默认不联网；AI 点评是可选能力，关闭时不影响识别与推荐。
- 浮窗是 Tkinter + Pillow 渲染的单张图片，不引入 Qt/WebView。
- 控制台是本地 HTTP + 静态 HTML/JS，不是第二套桌面 UI。

## 2. 模块依赖

```text
agent.py
├─ app.overlay.capture        Win32 截图、窗口查找、DPI、悬浮窗样式
├─ app.overlay.hotkey         全局热键
├─ app.overlay.hud            Pillow 卡片渲染 + Tk 窗口 + 滚动视口
├─ app.live.win32src          ROI-only GDI 抓帧
├─ app.live.sources           M1 兼容别名：CaptureSource / StaticFrameSource（无业务逻辑）
├─ app.live.sampler           采集线程 + 识别线程 + 去重
├─ app.replay                 M1 单图回放、fixtures 发现、草稿期望生成
├─ app.vision.assets          TemplateGroup / AssetBundle / AssetCache
├─ app.vision.pipeline        ROI -> 识别 Result
├─ app.vision.ocr             RapidOCR 名牌检测/识别/闭集校正
├─ app.vision.glyphs          字模兜底
├─ app.vision.schools         色度流派匹配 + 白色符文决胜
├─ app.vision.runes           白色符文掩码
└─ app.kb.recommend           Advisor：知识库 -> 推荐

run.py / app.server
├─ app.server                 控制台、图鉴、自检、上传 API
├─ app.kb.guides              攻略加载
├─ app.kb.index               检索
└─ app.kb.cards               卡牌/核心卡

tools/*                       单向生成资产、回放验收、准确率、发行包
```

依赖方向必须保持单向：`agent`/`server` 可以依赖 `app`，`app` 不能反向导入入口脚本；
`tools` 可以依赖 `app`，运行时不能依赖 `tools`。

## 3. 运行线程

| 线程 | 职责 | 约束 |
| --- | --- | --- |
| Tk 主线程 | 浮窗显示、拖动、滚轮、热键事件轮询 | 不做识别/截图重活 |
| `live-capture` | 抓 ROI、稳定性判断、5 帧聚合 | 抓帧前按需隐藏浮窗 |
| `live-recognition` | 识别、查库、推送结果 | 不直接操作 Tk |
| `control-panel` | HTTP 控制台 | 不阻塞主循环 |

浮窗隐藏由 `Agent._before_live_capture` 通过 `root.after(0, ...)` 投递到 Tk 线程，并用
`_capture_gate` 等待；抓完由 `_after_live_capture` 恢复。实时结果经 `live_queue` 回主线程，
只允许主线程调用 `hud.show`。

## 4. 识别数据流

1. `WindowFrameSource.state()` 找游戏窗口，拿到客户区尺寸。
2. `grab(icons_roi)` / `grab(nameplates_roi)` 只抓 ROI，不抓全屏。
3. `LiveSampler` 用底部 8 个书包图标判断是否进入选人界面；不稳定时保持/重采。
4. 5 帧中位数聚合，过滤指针和窗口 resize 造成的异形帧。
5. 流派：色度模板 + 白色符文决胜；英雄：RapidOCR 闭集校正，失败回退字模。
6. `recognize_rois` 输出槽位、英雄名、流派 ID、置信度、耗时。
7. `Advisor.recommend` 查知识库并排序；没有命中时返回明确的“暂无攻略”，不猜。
8. `render_result` 为每个识别到的英雄渲染完整区块；超过视口高度时滚动。

### 4.1 静态回放（M1）

`app/live/sources.py` 只提供无逻辑别名：`CaptureSource = FrameSource`、
`StaticFrameSource = ImageFrameSource`。静态图与实时窗口都通过 `grab(roi)` / `state()` 进入同一条
`recognize_rois` 管线，不另造输入抽象，也不改 `LiveSampler` 签名。

```powershell
python -m app --replay tests/fixtures/screenshots/draft001_1800x1118.png
python -m app --generate-expected <截图> --out tests/fixtures/expected
```

fixture 契约：`tests/fixtures/expected/<stem>.json` 与
`tests/fixtures/screenshots/<stem>.png` 同名；JSON 至少含 `heroes`，可选
`schools.enabled` / `schools.banned` / `min_confidence`。`tests/conftest.py` 与
`tests/test_replay.py` 自动发现并逐条跑真实图。两条旧 holdout 的图片和标签已迁入 fixtures；
`samples/validation/holdout/meta.json` 只保留 `client` / `expected_file` 引用，避免两套标签源。
pytest 是 dev-only 依赖，绝不进入运行时或发行包；真实验证图仍受体积/git 卫生约束。

## 5. 数据与资产契约

### 5.1 只读资产（随包、运行时不得写）

| 目录 | 内容 | 生成方式 |
| --- | --- | --- |
| `data/recognize/` | `layout.json`、色度模板、符文模板、字模 | `tools/build_school_*.py`、`build_glyph_templates.py` |
| `data/templates/` | 旧头像/流派图标模板 | `tools/build_templates.py` |
| `data/art/` | 60 立绘 + 120 天赋/大招图标 | `tools/import_art_assets.py` |
| `static/` | 控制台 HTML/JS/CSS | 手工维护，随包只读 |
| `data/*.json`（英雄/卡牌/规则/来源） | 知识库主数据 | `tools/import_game_data.py` |

规则：

- 进包资产必须由 `tools/` 单向生成；不手工改生成物。
- 资产来源在 `docs/DATA_SOURCES.md` 或对应目录 README 登记。
- 模板重建不得覆盖品牌资产；识别模板与品牌资产分目录。
- 运行时**不写随包资产目录**。任何“保存攻略/设置”的路径必须落在用户数据区。

### 5.2 用户数据（可写）

当前实际写入位置（均在程序目录的 `data/` 下）：

| 路径 | 内容 | 备注 |
| --- | --- | --- |
| `data/settings.json` | 设置、可选 LLM 配置 | `save_json` 已原子写入 |
| `data/server_url.txt` | 本次控制台地址 | 运行时生成 |
| `data/overlay_position.json` | 浮窗位置 | 运行时生成 |
| `data/captures/` | 手动截图 | 运行时生成 |
| `data/uploads/` | 控制台上传截图 | 运行时生成 |
| `data/guides/*.md` | 攻略 | 控制台可直接编辑，见下方债务 |

**已知债务**：`data/guides/` 同时是随包知识库和控制台可编辑目录。安装到
`Program Files` 时可能没有写权限，升级也可能覆盖用户修改。计划把用户攻略迁移到
`%APPDATA%\XuanJiHelper\guides\` 的覆盖层，随包 `data/guides` 只读；迁移完成前，发行版
说明必须提醒用户“免安装目录才可直接编辑攻略”。

### 5.3 未来用户预设（计划，未实现）

- 位置：`%APPDATA%\XuanJiHelper\profiles.json`（Windows），程序目录只读。
- 格式：带 `schema_version` 的 JSON；加载时迁移，不静默丢弃未知字段。
- 写入：临时文件 + `os.replace` 原子替换。
- 合并：字段级覆盖；预设空字段保留系统值，禁止整体替换。
- 预设优先级高于系统推荐，但两者都可查看。

详细语义（overlay 还是单文件、卡牌清单来源、空值/数组规则）见 [ADR](ADR.md) 的待决项。

## 6. 模板分组

`data/recognize/layout.json` 定义：

- `reference_resolution`：当前参考宽度 1800。
- `template_groups`：`hd`（<1920）、`fhd`（1920–2559）、`qhd`（≥2560）。
- `AssetCache.for_width(client_width)` 选择分组并缓存 bundle；`LiveSampler` 在客户区宽度
  变化时切换，失败保留旧 bundle。

现状：三个分组仍指向同一批 `schools_chroma.json` / `school_runes.json` / `glyphs.json`，
参考宽度都是 1800。分组是**接线完成、模板未分采**，不能宣称已按 4K 校准。重采时必须给
每组独立 `reference_width`，并加“不同分组文件不应相同”的测试；在此之前不要反转现有共享
缓存测试来锁死错误实现。

## 7. 品牌资产与启动画面（计划，未实现）

当前 `tools/build_release.py` 未传 `--icon`，也没有启动画面。接入时按下述位置：

- `assets/brand/app.ico`：多尺寸 16/24/32/48/64/128/256；源图 RGBA 正方形 PNG，非正方形先
  等比缩放并居中填充。
- `assets/brand/source.png`：品牌源图；不与 `data/recognize/` 模板混放。
- PyInstaller `--icon` 只影响 exe 文件和资源管理器，不影响窗口标题栏/任务栏；窗口图标要在
  Tk 里单独设置，任务栏分组用 AppUserModelID。
- 启动画面用 `--splash`；进入主循环后调用 `pyi_splash.close()`，并加 `try/except`（该模块
  只在打包后存在）。内置闪屏文字避免洋红色，它可能被当作透明色。

## 8. 已知限制

- 独占全屏、受保护画面或反作弊渲染可能让截图失败；优先无边框窗口。
- 本机未安装 RapidOCR 时走字模兜底；本地发行包因此明显小于 CI 的 OCR 包。
- 真实帧 holdout 只有 9 组，准确率结论只覆盖这九张图；其中 4 张全屏压力样本和 B/D 两组未标注流派，C 组因字模无法识别未入库。
- 预设功能未实现；当前只有系统推荐。
- 无应用图标/启动画面/代码签名，Windows SmartScreen 可能提示未知发布者。
