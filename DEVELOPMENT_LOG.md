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
- **状态**：防重复已完成；真实样本 6 组（新增 4 张 1080p/1600p 全屏截图），10 组门槛未达成。

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

## 2026-11-21 “未核验”不是免责声明

- **现象**：CI 日志、Release 资产、第三方依赖状态经常在没当场确认时被写成“应该没问题”。
- **根因**：把“上次成功”或“文件名存在”当成当前证据；报告和总结天然倾向于给结论。
- **正确做法**：无法当场验证的状态一律写 **未核验**，并说明卡在哪一步（没装依赖、API 限流、
  没有截图、没启动 exe）。准确率结论必须带样本量和来源；`n < 10` 不写成达标依据。
- **证据**：`RULES.md` 第 3 节；`PLAN.md` 基线表。
- **状态**：规则已落地，后续每次交付按此执行。
