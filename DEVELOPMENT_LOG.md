# DEVELOPMENT_LOG.md

> 开发教训记录：只写**根因**、**正确做法**和证据，不写“今天改了哪些文件”式的流水账。
> 流水账看 git log；这里回答“为什么当时会错、以后怎么避免”。架构背景见
> [ARCHITECTURE](ARCHITECTURE.md)，流程规范见 [RULES](RULES.md)。

## 记录格式

```text
### YYYY-MM-DD 标题
- 现象：
- 根因：
- 正确做法：
- 证据：
- 状态：已修复 / 部分完成 / 未解决
```

判定标准：一条记录如果不能指导下一次改动，就不该写进来。

## 2026-11-18 模板分档“有函数、无真实接线”

- **现象**：`layout.json` 已写 hd/fhd/qhd，函数和单测也能过，但实时识别仍像只有一套参考
  宽度；复核报告据此认为分档“部分完成（未接入）”。
- **根因**：能力只做到“函数 + 单测”层，没有一条测试证明 `agent`/`LiveSampler` 真的调用
  了它；后来虽然接入了 `AssetCache`，仍缺少源码级守卫，重构可以悄悄绕开。
- **正确做法**：新增能力必须同时交付“实现 + 实时链路引用 + 端到端或源码级测试”。只在
  `app` 里写函数、再配一个单测，不算完成。`tests/test_template_groups.py` 现在断言
  `agent.py` 含 `AssetCache(`、`asset_provider=self._live_assets_for_width` 和
  `.for_width(client_width)`。
- **证据**：`e2a1cdb feat: select recognition templates by resolution group`；
  `tests/test_template_groups.py::AssetCacheTest::test_live_agent_uses_the_resolution_aware_cache`。
- **状态**：接线已修复；模板仍共用同一批文件，见下一条。

## 2026-11-19 holdout 可能被“同屏连拍/旧图”充数

- **现象**：holdout 曾只有空目录；如果为了凑门槛把旧验证图复制进来，或连续截同一画面，
  指标会很好看，但样本并不独立。
- **根因**：导入器只按文件名/数量判断，没有校验图片内容；CI 只要求 `--min-cases 2`，
  固定验证集和 holdout 也容易混着算。
- **正确做法**：真实帧去重必须看**解码后的像素摘要**（同一帧换 PNG/JPEG 编码也要识别），
  再叠加“分辨率 + 英雄 + 流派”完全相同的拒绝规则；holdout 单独一个 `meta.json`，CI 单独
  一步，门槛用 `--min-cases` 显式写出。不能为了凑 10 组造图。
- **证据**：`tools/import_validation.py` 的 `image_digest` / `_existing_digest` /
  `_same_labels`；`tests/test_validation_import.py` 的重复内容、同尺寸同标签用例；
  `.github/workflows/ci.yml` 的 holdout 步骤。
- **状态**：防重复已完成；真实样本 10 组（新增 4 张 1080p/1600p 全屏截图和 4 张 2560×1390 四英雄截图），已达门槛；C 组作为“极寒掌控者”真实失败样本入库。

## 2026-11-19 三个模板组指向同一套 1800px 模板

- **现象**：`hd`/`fhd`/`qhd` 分组存在，但都指向 `schools_chroma.json`、
  `school_runes.json`、`glyphs.json`，`reference_width` 都是 1800。
- **根因**：先加了分组元数据和选择逻辑，没有同步采集各分辨率模板；更危险的是，如果测试
  只比较“三组都能加载”，就会把“三组完全相同”锁成正确行为。
- **正确做法**：每组独立采集模板、独立 `reference_width`；测试必须断言不同分组指向不同
  文件（或在显式共享时有白名单理由），并保留 hd 回退和警告日志。完成前不对外宣称 4K
  已校准。
- **证据**：`data/recognize/layout.json`；`tests/test_template_groups.py` 当前仍允许共享，
  因为模板尚未分采；`docs/ROADMAP.md` 记录为待办。
- **状态**：未解决（接线完成，模板未重采）。

## 2026-11-18 窗口版打包后启动即崩溃

- **现象**：PyInstaller `--windowed` 打包的 exe 启动后立刻退出；源码运行正常。
- **根因**：窗口模式下 `sys.stdout` / `sys.stderr` 为 `None`，代码里的 `print` 触发
  `AttributeError`，而窗口模式没有控制台可看 traceback。
- **正确做法**：入口最先调用 `ensure_std_streams()`，把缺失的标准流重定向到 `os.devnull`；
  打包冒烟测试必须实际启动 exe，不能只检查文件存在。
- **证据**：`agent.py` 的 `ensure_std_streams`；`0352312 fix: keep windowed builds from
  crashing on missing stdio`；`tests/test_agent_streams.py`。
- **状态**：已修复。

## 2026-11-18 识别完成后浮窗持续闪烁

- **现象**：自动识别出结果后，浮窗仍反复在“结果/已就绪”之间闪，尤其选人动画未完全静止时。
- **根因**：两处叠加。其一，`LiveSampler` 在探针看到 `WATCHING` 时清空上一轮已接受结果，
  瞬时动画导致反复 5 帧重采；每次重采都要隐藏浮窗。其二，`Agent` 在 `WATCHING`/`STALE`
  时立刻用 `show_ready()` 替换分析卡，形成“结果→就绪→结果”的视觉跳变。
- **正确做法**：瞬时 `WATCHING` 保留上一轮已接受结果，只有 `IDLE` 才清空；展示层加宽限期
  （`LIVE_READY_GRACE_SECONDS = 4.0`），持续丢失超过宽限期才回到就绪；回到同一选人界面时
  恢复上一张分析图。不要把“单帧探针失败”等同于“界面消失”。
- **证据**：`987054e fix: debounce live HUD state flapping`；
  `tests/test_live_hud_state.py`；`tests/test_sampler.py::test_watching_keeps_last_accepted_round`。
- **状态**：已修复。

## 2026-11-19 CI 发行包比本地大很多

- **现象**：GitHub Release 的 zip 约 123 MB，本地构建约 43 MB。
- **根因**：CI 安装完整 `requirements.txt`（含 RapidOCR/OpenCV），PyInstaller 会收集其原生
  库；本机未安装 RapidOCR，走字模兜底，所以包小。这不是打包脚本漏文件。
- **正确做法**：文档同时写清两种包的差异和 OCR 可用性，不把“包小”当成优化成绩，也不把
  “CI 包大”当成缺陷；用户下载页说明包含 OCR、体积较大。
- **证据**：`.github/workflows/release.yml`；`docs/RELEASE.md`；Release v0.2.3 资产大小
  123,146,873 字节；本地 zip SHA256 `a34c45fb...`。
- **状态**：已记录，非缺陷。

## 2026-11-21 文档与实际仓库不一致

- **现象**：复核报告写“现有 UI 是 PyQt”；README 链接了不存在的 `docs/ARCHITECTURE.md`；
  仓库没有 PRD/RULES/ARCHITECTURE/DEVELOPMENT_LOG/PLAN/ADR 六件套。
- **根因**：文档按印象或旧报告写，没有先核对依赖、目录和入口；也没有测试防止文档链接失效。
- **正确做法**：写文档前先读 `requirements.txt`、入口、目录和测试；六件套放仓库根目录，
  README 用根目录链接；“PyQt”这类技术判断必须有依赖或代码证据。新增
  `tests/test_repo_hygiene.py` 检查六件套存在、README 链接和关键契约。
- **证据**：`tests/test_repo_hygiene.py`；根目录六份文档；`requirements.txt` 仅
  numpy/Pillow/rapidocr。
- **状态**：已修复。

## 2026-11-23 M2 调试浮层的坐标空间与大图适配

- **现象**：第一版调试预览把底部模板框画到了屏幕左上方，OCR 框整体偏高；直接打开 2560×1390
  截图时浮层比 1080p 屏幕还大，底部被裁掉。
- **根因**：`runs` / `plate_boxes` / `glyph_boxes` 都是相对各自 ROI 的局部坐标，绘制层当成了
  客户区绝对坐标；`DebugOverlay` 直接使用原图，没有按屏幕工作区缩放。
- **正确做法**：`build_debug_frame` 分别加上图标条/名牌 ROI 的左上偏移；`DebugOverlay` 用
  `fit_debug_image` 缩放到屏幕 90%×85%，而保存 PNG 仍用原图。坐标空间必须有测试断言，
  不能只看“有没有框”。调试模式独占屏幕，主浮窗让位；Esc/关闭必须通过回调恢复 HUD，
  否则用户会只剩一张无法操作的调试图。
- **证据**：`app/vision/debugframe.py`、`app/overlay/debug.py`、
  `tests/test_debug_overlay.py`；本机 GUI 冒烟（临时截图已清理）。
- **状态**：已修复；M2 调试浮层可用。

## 2026-11-23 M1 回放复用输入层，pytest 只作开发依赖

- **现象**：已有 `FrameSource`/`ImageFrameSource`，但真实图回归没有统一入口；测试直接喂数组，
  无法从用户截图复现同一条识别链路。
- **根因**：输入抽象只服务实时线程，离线验收另走 `tools/live_recognize.py`，缺少 fixtures
  契约和自动发现；把 pytest 当成可选工具，导致收集范围不固定。
- **正确做法**：`app/live/sources.py` 只做无逻辑别名（`CaptureSource = FrameSource`、
  `StaticFrameSource = ImageFrameSource`），`app.replay`/`python -m app --replay` 走同一协议；
  fixtures 的期望标签是唯一来源，旧 holdout 只保留引用。pytest 放 `requirements-dev.txt`
  （`-r requirements.txt` + 精确锁版本），CI 分两步安装，PyInstaller 显式
  `--exclude-module pytest/_pytest/tests/test`，不让测试依赖进入发行包。
- **证据**：`app/live/sources.py`、`app/replay.py`、`app/__main__.py`、
  `tests/fixtures/`、`tests/test_replay.py`、`tests/conftest.py`、`requirements-dev.txt`、
  `tools/build_release.py`。
- **状态**：已实现；fixture 10/10，缺口 0，阈值只升不降；10 组 holdout 已接入 CI，门槛 8（保留 2 组余量）。

## 2026-11-23 “极寒掌控者”首字被 top5 挡掉

- **现象**：真实截图 C 的第一位英雄是 `极寒掌控者`，字模却返回 `null`；其他三位英雄正常。
- **根因**：`极` 是合法字模，但 16×16 紧裁切 + 游戏字体描边让它的最高分排到第 50，未进
  首字 top5；旧规则要求每个字都在 top5，整名被否决。按 top5 排名补字模或放宽 top5 都会把
  特殊名牌也放进候选，不能解决精度问题。
- **正确做法**：保留 top5 主路径；主路径找不到唯一名字时，按完整英雄名的逐字模板最高分
  重排，再要求绝对分数 ≥130、领先第二名 ≥20。真实名最低 147，特殊名牌最高 115，阈值有
  可解释间隔；C 组作为真实失败样本入库，而不是用 C 训练模板。
- **证据**：`app/vision/glyphs.py` 的 `_fallback_name`、`FULL_NAME_MIN_SCORE`、
  `FULL_NAME_MIN_MARGIN`；`tests/fixtures/expected/screenshot_2560x1390_c.json`；
  `tests/test_replay.py::FixtureDiscoveryTest::test_low_rank_character_is_recovered_by_full_name_fallback`。
- **状态**：已实现；10 组真实 fixture 全部通过，低于 10 组不得据此宣称全面达标。

## 2026-11-24 “关闭时零开销”只有描述，没有测量

- **现象**：M2 文档写“关闭时识别路径零额外开销”，但测试只证明 `_maybe_debug` 在禁用时
  提前 return，没有同一批 fixture 的开/关耗时对比。
- **根因**：把“代码路径看起来没做事”当成“可测的开销为零”；没有基准就容易在后续重构中
  悄悄把截图、建帧或 Tk 调用移到开关之前。
- **正确做法**：固定 N≥20 的真实 fixture A/B；关闭路径的 hook 成本要与识别耗时同量级比较，
  只构建 `DebugFrame` 的插桩开销设 5% 中位预算。调试窗口、截图和 PNG 保存属于“调试开启”
  的显式成本，不混进“识别路径零开销”的结论。
- **证据**：`tests/test_debug_benchmark.py`；当前 N=21，off 中位 276ms，on 中位 278ms，
  插桩开销 0.55%；禁用 hook ≈0.08µs/次。
- **状态**：已补测量；基准进入 pytest，CI 每次执行。

## 2026-11-24 holdout 的“10 组”不等于“10 组流派断言”

- **现象**：holdout 有 10 组，但只有 draft001、draft002、A 三组有非空 `schools`；其余 7 组
  的流派字段是 `null`。CI 绿灯实际主要验证英雄名，流派只覆盖 3 组。
- **根因**：门槛只数用例条数，不数每条上被断言的字段时间；`run_count 13` 这类流派缺陷
  没有足够的非空标签接住。
- **正确做法**：准确率报告同时输出 `schools_total` / `schools_unlabeled` /
  `schools_accuracy`，并在 CI 日志打印“schools_labeled=N/cases”；要么补人工流派标注，
  要么明确当前流派覆盖不足以证明回归。不能把用例数当成断言维度数。
- **证据**：`tools/run_accuracy.py` 的 `compute_metrics` / `[accuracy]` 汇总；
  `tests/test_accuracy.py` 的流派覆盖测试；当前 3/10。
- **状态**：度量已加；7 组流派标签仍待人工补，不能用猜测填。

## 2026-11-24 M3 标注和模板分组的“身份”

- **现象**：归一化标注如果另建目录，会与 `tests/fixtures/expected/` 形成第二套标签源；
  三个分辨率组如果继续共享 matcher，跨分辨率问题会被“同一对象”掩盖。
- **根因**：把“文件相同”当成“行为相同”；把“分组存在”当成“缩放已实现”。
- **正确做法**：annotation 只存在 expected JSON 的可选块；`app.vision.annotation` 负责
  0–1 校验、缩放和原子写回；每组独立 matcher + 独立 `reference_width`，但明确模板文件
  仍共享，不宣称 4K 校准；2560 图标条按 `base_run_w` 缩放最小 run 宽，过滤细碎高光。
- **证据**：`app/vision/annotation.py`、`tools/annotate_fixture.py`、
  `tests/test_annotation.py`、`tests/test_scaling.py`、`tests/test_template_groups.py`。
- **状态**：M3 归一化标注、跨分辨率断言、2560 run 数修复已完成；独立模板重采仍未做。

## 2026-11-26 浮窗遮挡图标条被误判成“换人”

- **现象**：已经显示识别结果后，浮窗仍周期性闪一下；日志里并没有新英雄。
- **根因**：`_last_icons` 是隐藏浮窗后采到的干净帧，下一次探针却是在浮窗可见时抓的。
  多英雄浮窗底部会压住图标 ROI 的上沿，遮挡本身足以超过 `diff_ratio` 的 0.008 阈值，
  于是每个探针都触发一次 5 帧抓取；每次抓取都要隐藏/恢复浮窗。
- **正确做法**：探针比较前用 `roi_overlap_rects` 把浮窗屏幕矩形与图标 ROI 求交，
  再用 `diff_ratio_masked` 排除交集；浮窗位置从 `Hud.last_position` / `last_image` 的缓存读取，
  不在抓帧线程碰 Tk。不要靠“禁止用户把浮窗拖到图标上”来规避。
- **证据**：`app/live/stability.py`、`app/live/sampler.py`、`agent.py`、
  `tests/test_sampler.py`（遮挡合成源只抓一次）、`tests/test_live_hud_state.py`（ROI 交集）。
- **状态**：已修；浮窗仍会在第一次需要抓新结果时短暂隐藏，这是抓干净帧的必要成本，
  但不再因结果不变而周期性闪。

## 2026-11-26 启动菜单把“可选网页”变成必经步骤

- **现象**：用户双击启动器后先看到一个 1/2/3/4 菜单；只想用浮窗时也要先选择，网页攻略库
  和浮窗入口被混在同一个启动决策里。
- **根因**：把“浮窗 + 网页 + 设置”当成启动模式，而不是把网页当成浮窗里的按需功能；
  启动器承担了入口分发，界面里没有直达入口。
- **正确做法**：启动器只负责找 Python 并直接启动 `agent.py`；浮窗右上角提供
  「设置 / 攻略库」按钮，点击后用 `/?open=guides` 直达网页的攻略编辑弹窗；启动时不自动
  打开浏览器。网页仍是本地服务，不影响“离线可用”。
- **证据**：`启动助手.bat`（无 `choice`/菜单）、`agent.py::open_guide_editor`、
  `app/overlay/hud.py` `settings_button`、`static/app.js` 的 `?open=guides` 分支、
  `tests/test_launcher.py`、`tests/test_guide_editor.py`。
- **状态**：已实现并测试；HUD 按钮在 1920×1080 下为 118×24，位于右上角。

## 2026-11-21 “未核验”不是免责声明
