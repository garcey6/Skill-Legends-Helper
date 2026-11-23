# Changelog

本项目的重要变更记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循语义化版本。

## [Unreleased]

### 新增

- M1 静态回放：复用 `FrameSource` 增加 `CaptureSource` / `StaticFrameSource` 兼容别名，
  新增 `python -m app --replay <截图>` 和 `--generate-expected`，fixtures 自动发现并逐条断言
  英雄、流派与可选置信度下限。
- M2 调试浮层：`Alt+D`（可配置）按需显示 ROI、OCR 名牌框、模板框/分数与失败原因；
  Tkinter 置顶浮层支持拖动、`1/2/3` 分层、`A` 全开、`S` 保存标注 PNG，位置与 PNG 写入
  `%APPDATA%\SkillLegendsHelper\`；调试关闭时不增加识别开销。
- 真实 fixture 契约：`tests/fixtures/screenshots/` + `tests/fixtures/expected/`；旧 holdout
  用例和新增真实截图统一迁入，holdout 元数据只保留引用。fixture 阈值升到 9，目标 10，
  pytest 每次输出 `9 / 目标 10，缺口 1`。

### 文档

- 新增项目基建六件套：`PRD.md`、`RULES.md`、`ARCHITECTURE.md`、`DEVELOPMENT_LOG.md`、
  `PLAN.md`、`ADR.md`；明确系统推荐与用户预设的边界、数据/资产契约、验收门槛阶梯和
  “未核验”状态规则。
- `AGENTS.md` 保留八荣八耻与硬约束，流程规范移入 `RULES.md`；补充“真实链路已引用”、
  “样本量/来源”和“未核验”三条协作原则。
- README 改为链接根目录六件套，修正此前指向不存在的 `docs/ARCHITECTURE.md`；文档明确
  当前 UI 是 Tkinter，不引入 PyQt。

### 测试

- 新增 4 张真实截图（1920×1080 / 2560×1600，30/80 亮度，含“特权解锁/随机”）和 3 张
  2560×1390 四英雄截图（A/B/D），真实帧 holdout 从 2 组增至 9 组，CI holdout 门槛从 6
  提到 8；全屏素材只登记已核对的字段，未逐图标复核的流派统一记为 `null`。C 组因字模
  无法识别“极寒掌控者”未入库，留作失败样本。
- 新增 `requirements-dev.txt`（继承运行时依赖，精确锁定 `pytest==9.2.0`）；CI 分两步安装
  运行时/开发依赖并改用 pytest；PyInstaller 显式排除 pytest 与测试目录。

### 计划中

- 补到 10 组真实帧 holdout（当前 9，差 1）后维持 CI 门槛 8，再逐步扩到 50–100 组。
- 为 hd / fhd / qhd 重新采样独立模板，而不是共用 1800px 参考模板。
- 代码签名、安装器与自动更新。

## [0.2.3] - 2026-11-19

### 新增

- 识别模板按分辨率分组：`layout.json` 增加 `reference_resolution` 与 `template_groups`
  （hd / fhd / qhd），自动识别在窗口宽度变化时切换模板组，共用文件时复用已加载的字模。
- 真实帧导入脚本 `tools/import_validation.py`：复制截图、归一化英雄别名、拒绝未知/重复
  标签，并原子写入 `meta.json`；`run_accuracy.py` 新增 `--min-cases` 门槛。
- 真实帧 holdout 接入 CI（当前 2 组，门槛 2），并新增数据集卫生检查：同一帧换名、或
  分辨率+标签完全重复会被拒绝。
- 免安装发行包脚本 `tools/build_release.py`：one-folder PyInstaller、安全数据清单、
  `release.json` 与 zip/SHA256；构建依赖单独放在 `requirements-build.txt`。
- `.github/workflows/release.yml`：推送 `v*` 标签自动构建并上传 GitHub Release。

### 修复

- 实时识别遇到瞬时 `WATCHING`（菜单淡入、符文动画、单帧抖动）时，浮窗会在分析卡与
  “浮窗已就绪”之间来回闪；现在保留已有分析卡，连续丢失选人界面超过 4 秒才回退到就绪
  状态，并保留上一轮稳定帧避免反复触发 5 帧抓取。

## [0.1.0] - 2026-11-18

### 新增

- 自动识别选人界面顶部实际出现的 1–5 个英雄，不再固定为 3 个；遇到“特权解锁/随机”名
  牌停止，未识别槽位保留为空，不猜测。
- 浮窗按英雄逐个展示完整卡片：评分、定位、路线、推荐理由、核心卡、开局路线；英雄较
  多时自动加高，超出屏幕可用滚轮查看。
- 五个仓库内 AI 协作技能（`.agents/skills`），覆盖识别模板、攻略库、OCR/字模、数据重
  建、回放验收。
- 离线准确率回归脚本 `tools/run_accuracy.py` 与 Windows GitHub Actions CI。
- MIT LICENSE、风险说明、Issue 模板、PR 模板与贡献者/代理约定（`AGENTS.md`）。

### 变更

- 统一启动入口 `启动助手.bat`：菜单选择浮窗+网页、仅网页、打开设置或退出。
- 浮窗改为游戏风格深色卡片，统一标题、分数、徽章与流派区域，提升文字对比度。

### 修复

- 未安装 OpenCV 时，白色符文兜底会把页面白边当成符文，导致“生命流”等被误判为未识别；
  现在用纯 NumPy 选中心连通域。
- PyInstaller `--windowed` 发行包里 `sys.stdout/stderr` 为 `None`，启动打印会崩溃；现在先
  把缺失的标准流指向空设备。
- 较暗窗口里单个汉字的上下/内部碎片会被拆成多个连通域，导致第二个名牌识别为空；现在
  按横向重叠合并同一字的碎片，并放宽名牌行聚类容差。
- 无 OpenCV 时用字模分组框给 OCR 提供候选名牌；OCR 不可用时继续走纯字模路径，并裁掉
  尾部空白的特殊槽位。
- 浮窗可见时抓帧导致名称牌与图标帧来源不一致，自动识别可能反复触发。
- 窗口尺寸变化产生的异形帧会让中位数聚合崩溃。
- `CAPTURING` 回到 `READY` 时重复推送相同结果。
