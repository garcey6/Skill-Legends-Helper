# AGENTS.md

> 这是给 AI/协作者的最小入口：硬约束、命令、八荣八耻。完整开发流程见
> [RULES](RULES.md)，产品边界见 [PRD](PRD.md)，架构与数据契约见
> [ARCHITECTURE](ARCHITECTURE.md)，计划见 [PLAN](PLAN.md)，历史决策/待决项见
> [ADR](ADR.md)，踩坑记录见 [DEVELOPMENT_LOG](DEVELOPMENT_LOG.md)。

## 项目

《选技大乱斗》本地浮窗助手：Tkinter 浮窗 + 本地 HTTP 控制台，离线识别选人界面的英雄
名与流派图标，再用本地攻略库给出推荐。识别链路不依赖 LLM，默认不联网。

- 工作目录：仓库根目录。
- 运行时依赖只允许 `numpy`、`Pillow`、`rapidocr_onnxruntime`；新增依赖前先说明理由。
  `pytest` 只允许放在 `requirements-dev.txt`，不得进入运行时或发行包。
- 平台：Windows 10/11；Python 3.10+。
- 识别资产由 `tools/` 下的脚本生成，不手工编辑生成物。
- 当前浮窗是 Tkinter，网页控制台是本地 HTML/JS；不要引入 PyQt 或第二套 UI 框架。

## 常用命令

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/validate_cases.py --strict
python tools/run_accuracy.py --strict --min-cases 2
python tools/run_accuracy.py --meta samples/validation/holdout/meta.json --strict --min-cases 6
python -m app --replay tests/fixtures/screenshots/draft001_1800x1118.png
python -m tools.live_recognize --replay samples/frames/draft_001
```

如果本机没有 `python`，使用项目 `启动助手.bat` 里配置的 Python。
pytest 会输出 fixture 数/目标 10/缺口；fixture 阈值只升不降。固定验证集用
`--min-cases 2`，真实 holdout 当前用 `--min-cases 6`；都不是长期目标，样本增加后按
[PLAN](PLAN.md) 阶梯提高，holdout 达到 10 组后提到 8。

## 仓库内 AI 技能

修改对应领域前，先读 `.agents/skills/<name>/SKILL.md`：

- `recognition-templates`：`data/recognize/layout.json`、色度模板、符文模板的重建与验收。
- `guide-kb`：`data/guides/`、`tools/build_guides.py`、`tools/verify_guides.py`。
- `ocr-glyphs`：英雄名闭集 OCR、字模兜底、未知字处理。
- `data-rebuild`：游戏数据、卡牌、英雄立绘和生成资产的导入流程。
- `release-replay`：回放验收、准确率回归、发版前检查清单。

## 硬约束

- 保持“闭集校正 + 不确定时返回 null”的识别策略，不要为了让结果好看而猜名字。
- 不要改变评分权重、流派阈值或运行时数据，除非任务明确要求并附 before/after 验证。
- 浮窗宽度保持 620；内容超出屏幕时滚动，不缩小正文到不可读。
- 不修改游戏文件、内存，不模拟键鼠；只读取屏幕像素。
- 不提交 `data/settings.json`、`data/server_url.txt`、截图上传目录或任何密钥。
- 运行时只读随包资产；用户数据写用户目录。识别层只输出标识，不硬编码攻略文案。
- 先写失败测试，再实现；提交保持小而可回滚。
- 没有当场验证的状态写“未核验”，不得推断为通过。

## 协作原则（八荣八耻）

以认真查询为荣，以瞎猜接口为耻。
以寻求确认为荣，以模糊执行为耻。
以人类确认为荣，以自作主张为耻。
以复用现有代码为荣，以重复造轮子为耻。
以保持代码简洁为荣，以过度设计为耻。
以主动测试为荣，以跳过验证为耻。
以诚实无知为荣，以假装理解为耻。
以谨慎重构为荣，以盲目修改为耻。

补充三条（来自 2026-11-21 基建复核）：

- 以**真实链路已引用**为荣，以“只写函数 + 单测就算完成”为耻。
- 以**样本量、来源、运行环境写清楚**为荣，以 `n < 10` 就宣称达标为耻。
- 以**写明“未核验”**为荣，以推断“应该通过”为耻。

## 提交前

```powershell
git diff --check
python -m pytest -q
python tools/validate_cases.py --strict
```

涉及识别参数时再加 `python tools/run_accuracy.py --strict --min-cases 2`；涉及 holdout 时
再加 `--meta samples/validation/holdout/meta.json --min-cases 6`。文档使用中文；用户可见文案也用中文，
技术标识符保持英文。

小改（修 bug、调阈值、补测试）至少更新 [DEVELOPMENT_LOG](DEVELOPMENT_LOG.md) 和
[PLAN](PLAN.md)；能力级改动按 [RULES](RULES.md) 第 4 节更新六件套。
