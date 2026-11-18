# Changelog

本项目的重要变更记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循语义化版本。

## [Unreleased]

### 新增

- 识别模板按分辨率分组：`layout.json` 增加 `reference_resolution` 与 `template_groups`
  （hd / fhd / qhd），自动识别在窗口宽度变化时切换模板组，共用文件时复用已加载的字模。
- 真实帧导入脚本 `tools/import_validation.py`：复制截图、归一化英雄别名、拒绝未知/重复
  标签，并原子写入 `meta.json`；`run_accuracy.py` 新增 `--min-cases` 门槛。
- 免安装发行包脚本 `tools/build_release.py`：one-folder PyInstaller、安全数据清单、
  `release.json` 与 zip/SHA256；构建依赖单独放在 `requirements-build.txt`。

### 计划中

- 扩充 50–100 组真实帧 holdout 验证集。
- 在 CI 中发布签名后的发行包。

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
- 较暗窗口里单个汉字的上下/内部碎片会被拆成多个连通域，导致第二个名牌识别为空；现在
  按横向重叠合并同一字的碎片，并放宽名牌行聚类容差。
- 无 OpenCV 时用字模分组框给 OCR 提供候选名牌；OCR 不可用时继续走纯字模路径，并裁掉
  尾部空白的特殊槽位。
- 浮窗可见时抓帧导致名称牌与图标帧来源不一致，自动识别可能反复触发。
- 窗口尺寸变化产生的异形帧会让中位数聚合崩溃。
- `CAPTURING` 回到 `READY` 时重复推送相同结果。
