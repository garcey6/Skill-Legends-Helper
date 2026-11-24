# ADR.md

> 架构决策记录（Architecture Decision Record）。只记录**已经影响代码结构的决定**和
> **实现前必须定死的待决项**；普通实现细节留在 [ARCHITECTURE](ARCHITECTURE.md)。
>
> 状态：`已接受` / `已接受（实现部分）` / `待决` / `已废弃`。待决项不得在代码里“边写边猜”。

## ADR-001 英雄名采用闭集校正 + 不确定返回 null

- **日期**：2026-11-17
- **状态**：已接受
- **背景**：英雄名是游戏内固定 60 人集合，但截图会受分辨率、字体、遮挡和 OCR 噪声影响。
  开放词表识别容易把相似字拼成不存在的名字，或者把低置信度结果伪装成确定答案。
- **决策**：RapidOCR 的输出必须映射到已知英雄闭集；映射不上或置信度不足时返回 `null`，
  由字模兜底或让对应槽位保持未识别。禁止用编辑距离/模糊匹配“猜”一个名字。
- **备选**：开放词表 OCR；LLM 自由识别；按相似度强行取最近英雄。
- **后果**：未知英雄会显示未识别，而不是错误答案；新增英雄必须更新字库/闭集数据。准确率
  指标要区分“识别错”和“拒识”，不能用拒识率换准确率。
- **证据**：`app/vision/ocr.py`；`tests/test_dynamic_heroes.py`；`RULES.md` 第 5 节。

## ADR-002 识别模板按客户区宽度分档（hd / fhd / qhd）

- **日期**：2026-11-18
- **状态**：已接受（实现部分）
- **背景**：模板在固定参考宽度下生成；不同分辨率/窗口尺寸下图标像素尺寸变化，单一模板会
  降低色度和字模匹配的稳定性。
- **决策**：按客户区宽度分三档：`hd < 1920`、`fhd 1920–2559`、`qhd >= 2560`。每档有独立
  `reference_width` 和 matcher 对象，模板文件可以独立；运行时通过 `AssetCache.for_width()`
  选择并缓存；切档失败保留旧 bundle，不中断识别。未覆盖宽度回退 `hd` 并打印警告。
- **备选**：所有分辨率共用一套模板；按 DPI 缩放而非宽度；运行时动态缩放模板。
- **后果**：分组选择和缓存已经接入 `agent`/`LiveSampler`；三档使用独立 matcher 对象和
  `reference_width` 1800 / 1920 / 2560，但模板文件仍共享，**不能宣称已按 4K 校准**。重采时
  必须让不同档指向不同文件，并加“不同档文件不应相同”的测试；独立 matcher 不是独立模板。
- **证据**：`data/recognize/layout.json`；`app/vision/assets.py`；
  `tests/test_template_groups.py`；`docs/ROADMAP.md`。

## ADR-003 运行时只允许三个第三方依赖

- **日期**：2026-11-17
- **状态**：已接受
- **背景**：项目要能离线、免安装、体积可控地分发给普通 Windows 玩家；每加一个依赖都会
  增大发行包和杀软误报面。
- **决策**：运行时依赖固定为 `numpy`、`Pillow`、`rapidocr_onnxruntime`。构建依赖
  （PyInstaller）放 `requirements-build.txt`，不进入运行时。新增运行时依赖必须先有 ADR，
  说明体积、许可证、可选降级和卸载路径。
- **备选**：引入 OpenCV、PyQt、云 OCR、数据库。
- **后果**：部分图像处理用 numpy/Pillow 手写；没有 OpenCV 时走降级路径（符文连通域、字模
  兜底）。发行包分 OCR 完整包和字模兜底包，体积不同，文档必须写清。
- **证据**：`requirements.txt`；`requirements-build.txt`；`app/vision/runes.py` 的
  `_fallback_component`。

## ADR-004 资产由 tools 单向生成，运行时只读

- **日期**：2026-11-17
- **状态**：已接受（存在已知例外）
- **背景**：模板、立绘、知识库如果允许运行时改写，升级会覆盖用户修改，回滚也无法复现；
  手工编辑生成物会让“数据从哪来”不可追踪。
- **决策**：`data/recognize/`、`data/templates/`、`data/art/` 和 `static/` 是随包只读资产，
  只能由 `tools/` 下的脚本生成；运行时不得写入。用户数据（设置、截图、预设）写用户数据区，
  不写随包资产。所有 JSON 写入使用临时文件 + `os.replace` 原子替换。
- **备选**：运行时直接编辑模板/攻略；把用户数据放在程序目录旁边。
- **后果**：当前 `data/guides/` 仍可被本地网页控制台直接编辑，这是**已知债务**：安装到
  `Program Files` 时可能没有写权限，升级也可能覆盖。迁移方案是随包攻略只读、用户攻略写
  `%APPDATA%\XuanJiHelper\guides\` 覆盖层；在迁移完成前，发行说明必须提醒用户。设置、
  截图、上传、浮窗位置目前也在 `data/`，属于待迁移用户数据。
- **证据**：`app/config.py` 的 `DATA_DIR`/`save_json`；`docs/RELEASE.md`；`ARCHITECTURE.md`
  第 5 节。

## ADR-005 CI 使用 Windows 运行器

- **日期**：2026-11-19
- **状态**：已接受
- **背景**：截图、DPI、窗口查找和 Tkinter 都是 Windows 特定路径；Linux 容器无法真实覆盖。
- **决策**：GitHub Actions 使用 `windows-latest` + Python 3.11；分两步安装
  `requirements.txt` 和 `requirements-dev.txt`（pytest 只进 dev）；依次跑 pytest、固定验证集、
  holdout、打包。Release 工作流由 `v*` 标签触发。
- **备选**：Ubuntu + mock Win32；只在本地跑测试。
- **后果**：CI 成本更高、启动更慢，但能覆盖真实平台。没有 RapidOCR 的本地环境会跳过部分
  OCR 用例；文档必须写成“146 通过、3 跳过”这类当场核验的数字，不得沿用旧值。
- **证据**：`.github/workflows/ci.yml`；`.github/workflows/release.yml`。

## ADR-006 用户预设的存储形态（待决）

- **日期**：2026-11-21
- **状态**：待决
- **背景**：预设是用户资产，必须抗升级、可迁移、可手工备份。当前只有系统推荐，预设代码
  未实现。
- **候选**：
  1. 单文件 `%APPDATA%\XuanJiHelper\profiles.json`，全部英雄一个数组；
  2. 每英雄一个文件，目录作为 overlay；
  3. 随包默认 + 用户 overlay 两层合并。
- **需要定死的点**：单文件并发写如何原子替换；每英雄文件的命名/清理；overlay 删除语义；
  是否允许导出/导入覆盖。
- **倾向（未接受）**：单文件 + `schema_version` 起步，量大了再拆 overlay；无论哪种，都必须
  原子写、升级不丢、可手工备份。
- **决策前不得**：在代码里先写死路径或 schema；把预设写进 `data/` 随包目录。

## ADR-007 预设编辑器的卡牌清单来源（待决）

- **日期**：2026-11-21
- **状态**：待决
- **背景**：PRD 要求下拉/多选，不让用户手写 JSON；但卡牌库有 156 张，且用户可能想填库外
  组合。
- **候选**：
  1. 只允许从知识库选择，保证 ID 可校验；
  2. 知识库多选 + 自由文本补充，保存时保留原始文本；
  3. 完全自由文本，展示时再匹配。
- **需要定死的点**：库外条目如何显示/排序/去重；知识库升级后卡牌改名/删除如何处理；
  是否允许同一张卡重复。
- **倾向（未接受）**：以知识库 ID 为主，另留“补充说明”自由文本；库外卡不参与结构化评分。
- **决策前不得**：把自由文本直接当卡牌 ID 写进预设。

## ADR-008 预设与系统推荐的字段级合并语义（待决）

- **日期**：2026-11-21
- **状态**：待决
- **背景**：PRD 已定“预设优先、字段级覆盖”，但“空”的语义没定死；不同实现会导致用户只填
  核心卡时攻略被清空，或想清空某字段却清不掉。
- **候选**：
  1. `null`/缺失 = 继承系统值；空字符串 = 显式清空；数组 = 整体替换；
  2. 所有空值都继承；数组做并集；
  3. 逐字段声明合并策略（标量覆盖、数组替换/并集可选）。
- **需要定死的点**：空字符串与 `null` 是否等价；空数组是“清空”还是“继承”；多选卡牌的
  顺序是否保留；未知字段升级时保留还是丢弃。
- **倾向（未接受）**：`null`/缺失继承，`""` 和 `[]` 视为显式清空，数组整体替换、保留顺序；
  schema 带版本，迁移时保留未知字段。
- **决策前不得**：实现“整体替换”伪装成字段级合并；也不得把空数组静默当继承。

## ADR-009 M1 回放复用 FrameSource，fixtures 作为唯一真实图用例源

- **日期**：2026-11-23
- **状态**：已接受
- **背景**：识别管线已经有 `FrameSource` 协议、`ImageFrameSource` 和窗口源，但测试主要直接喂数组；
  新增 `python -m app --replay` 与真实图回归时，若另造一套输入抽象会让调试覆盖层和缩放逻辑分叉。
- **决策**：`app/live/sources.py` 提供无逻辑别名 `CaptureSource = FrameSource`、
  `StaticFrameSource = ImageFrameSource`；静态图与实时窗口都实现同一协议。M1 将两条旧 holdout
  用例的图片与期望标签迁到 `tests/fixtures/`，holdout 元数据只保留引用；pytest 为唯一测试入口，
  dev 依赖放 `requirements-dev.txt`（继承运行时依赖并精确锁版本），打包显式排除 pytest/tests。
- **备选**：新建 `CaptureSource` 协议并让 `LiveSampler` 改签名；继续用直接数组测试；把 pytest 加进运行时依赖。
- **后果**：输入层不产生第二套抽象，识别管线签名不变；fixtures 是真实图用例的唯一标签来源，
  holdout 仍负责 10 例 CI 准确率。pytest 只是开发依赖，不进 `requirements.txt` 或发行包；代价是
  `tests/fixtures` 仍需遵守图片体积/git 卫生规则，且 M3 必须在 fixtures 上增加跨分辨率用例。
- **证据**：`app/live/sources.py`、`app/replay.py`、`tests/test_replay.py`、
  `requirements-dev.txt`、`tools/build_release.py`、`tests/fixtures/`。

## ADR-010 M2 调试浮层使用 Tkinter + 只读 DebugFrame

- **日期**：2026-11-23
- **状态**：已接受
- **背景**：需要在不改 `recognize_rois` 签名、不引入第二套 UI 框架的前提下显示 ROI、OCR 框、
  模板框、置信度和耗时；普通识别路径不能为调试付出采集或绘制成本。
- **决策**：`app/vision/debugframe.py` 只从既有识别结果构建 `DebugFrame`；`app/overlay/debug.py`
  用 Tkinter `Toplevel` + Canvas 显示，并用同一个 `render_debug_image` 生成 PNG。管线只增加
  附加字段 `plate_boxes`，不新增调试参数；Agent 在 `_maybe_debug` 第一行检查开关，关闭时不做
  截图、不构建帧、不碰 Tk。位置与 PNG 写 `%APPDATA%/SkillLegendsHelper/`。
- **备选**：改 `recognize_rois` 返回调试对象；新建 PyQt/WebView 调试窗口；调试时在 HUD 内叠加。
- **后果**：运行时依赖不增加；调试与正常路径共用同一份识别结果，避免“浮层显示的是另一套结果”。
  代价是 OCR 候选本身没有框，调试帧只能在名牌 ROI 上做近似/检测框补充，框位置精度受当前
  ROI 实现限制。
- **证据**：`app/vision/debugframe.py`、`app/overlay/debug.py`、`tests/test_debug_overlay.py`、
  `tests/test_agent_debug.py`、`agent.py`。

## ADR-011 字模 top5 漏字时使用闭集全名兜底

- **日期**：2026-11-23
- **状态**：已接受
- **背景**：真实截图 C 的 `极寒掌控者` 首字 `极` 在 16×16 字模排序中只排到第 50，旧规则要求
  每个字都进 top5，导致整名返回 `null`；按 top5 补模板或放宽 top5 会把“特权解锁/随机”也
  放进候选。
- **决策**：保留 top5 主路径；主路径找不到唯一名字时，按完整英雄名的逐字模板最高分重排，
  仅接受平均分 ≥130 且领先第二名 ≥20 的闭集名字。`极寒掌控者` 作为真实失败样本入库，
  不用它训练字模；特殊名牌保持 `null`。
- **备选**：放宽 top5；给 `极` 补游戏字体字模；编辑距离/模糊匹配；OCR 失败直接返回 null。
- **后果**：不增加运行时依赖，C 恢复为 4/4；代价是兜底路径比 top5 路径更慢（C 组英雄识别
  约 286ms），且 10 组样本仍不足以证明对未见字体/分辨率全面成立。后续样本扩大时重新校准
  阈值，不得用这 10 组反推“100% 通用”。
- **证据**：`app/vision/glyphs.py` `_fallback_name` / `FULL_NAME_MIN_SCORE` /
  `FULL_NAME_MIN_MARGIN`；`tests/fixtures/expected/screenshot_2560x1390_c.json`；
  `tests/test_replay.py::FixtureDiscoveryTest::test_low_rank_character_is_recovered_by_full_name_fallback`；
  `tests/test_accuracy.py` 10 组 holdout 计数。

## ADR-012 fixture expected JSON 同时承载归一化标注，作为唯一来源

- **日期**：2026-11-24
- **状态**：已接受
- **背景**：M3 需要归一化坐标与跨分辨率断言。现有 `tests/fixtures/expected/*.json` 只存英雄/流派标签；
  如果另建 `annotations/` 目录，会重演 M1 消灭的“两套标签源”，只是分叉发生在几何层。
- **决策**：`tests/fixtures/expected/*.json` 继续作为 fixture 的唯一来源，并增加**可选**字段
  `annotation`：
  ```json
  {
    "base_resolution": {"width": 1800, "height": 1118},
    "features": [
      {"name": "hero_slot_1", "box": [0.1, 0.2, 0.3, 0.4]}
    ]
  }
  ```
  `box` 为归一化 `x, y, w, h`（0–1），`base_resolution` 记录标注时的图像尺寸；运行期按实际
  客户区尺寸缩放。M1 的发现、英雄/流派断言和 `--generate-expected` 不变；M3 的几何断言直接读
  同一份 expected，不再建第二套 fixture/annotation 目录。`layout.json` 仍是运行时 ROI 配置，
  不把 fixture 标注写进运行时资产。标注工具 `tools/annotate_fixture.py` 合并写入现有 expected，
  不覆盖英雄/流派字段。
- **备选**：新建 `tests/fixtures/annotations/`；expected 存绝对像素；把每张图的 ROI 写进 runtime layout。
- **后果**：一个 fixture 只有一份标签；旧 expected 可继续省略 `annotation`，逐张迁移；M3 的标注工具
  必须合并写入 existing expected，而不是覆盖英雄/流派字段。代价是 expected schema 变复杂，且跨分辨率
  用例必须显式写 `base_resolution`，不能靠文件名猜。
- **证据**：`tests/fixtures/expected/`、`app/vision/annotation.py`、`tools/annotate_fixture.py`、
  `app/replay.py`、`tests/test_annotation.py`、`tests/test_replay.py`、`PLAN.md` M3。

## 决策索引

| 编号 | 主题 | 状态 |
| --- | --- | --- |
| ADR-001 | 闭集校正 + null | 已接受 |
| ADR-002 | 宽度分档模板 | 已接受（实现部分） |
| ADR-003 | 三个运行时依赖 | 已接受 |
| ADR-004 | tools 单向生成 / 运行时只读 | 已接受（有例外） |
| ADR-005 | Windows CI | 已接受 |
| ADR-006 | 预设存储形态 | 待决 |
| ADR-007 | 卡牌清单来源 | 待决 |
| ADR-008 | 字段级合并语义 | 待决 |
| ADR-009 | M1 回放复用 FrameSource / fixtures 唯一来源 | 已接受 |
| ADR-010 | M2 调试浮层：Tkinter + 只读 DebugFrame | 已接受 |
| ADR-011 | 字模 top5 漏字时闭集全名兜底 | 已接受 |
| ADR-012 | fixture expected JSON 承载归一化标注，唯一来源 | 已接受 |
