---
name: release-replay
description: 发版前的回放、验证集和准确率回归流程；当准备提交、合并、打 tag 或发布 exe/源码包时使用。
---

# 发版与回放验收

## 触发条件

- 准备合并到 `main`、打 tag 或发布 Release。
- 修改了识别、OCR、布局、阈值、浮窗渲染或启动器。
- 用户报告“某个分辨率/某个英雄识别不对”，需要建立可复跑基线。

## 三层验证

1. **单元测试**：`python -m unittest discover -s tests -t .`
2. **固定验证集**：`python tools/validate_cases.py --strict`，覆盖 `samples/validation/`
   的真实窗口截图；当前只有 2 个 case，新增截图必须补 `meta.json`。
3. **回放夹具**：`python -m tools.live_recognize --replay samples/frames/draft_001`，检查
   识别链路而不是单帧函数。

新增准确率回归：

```powershell
python tools/run_accuracy.py --strict
```

输出 `slot_accuracy`、`hero_name_accuracy`、`exact_case_rate` 与 P50/P95 延迟。任何识别
参数改动都要附 before/after，而不是只跑一次“看起来过了”。

## 发版清单

- [ ] `git status` 干净，分支已合并，`CHANGELOG.md` 的 `Unreleased` 已整理。
- [ ] 上述三层验证通过；CI 通过。
- [ ] 浮窗用 1、3、5 个英雄截图各看一次；长卡片可滚动，不遮底部图标条。
- [ ] `启动助手.bat` 四个菜单项都能启动/退出，没有残留进程。
- [ ] 不提交 `data/settings.json`、`data/server_url.txt`、日志、截图上传和密钥。
- [ ] Release Note 说明风险：仅读屏幕、无键鼠模拟、反作弊/独占全屏可能失效。

## 回滚

识别参数改动导致回归时，优先回滚参数而不是继续调阈值；保留失败截图作为新夹具，再单独
修。发布包出问题时保留上一个可用 tag，不要强推覆盖已发布资产。
