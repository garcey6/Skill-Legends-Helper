# AGENTS.md

## 项目

《选技大乱斗》本地浮窗助手：Tkinter 浮窗 + 本地 HTTP 控制台，离线识别选人界面的英雄
名与流派图标，再用本地攻略库给出推荐。识别链路不依赖 LLM，默认不联网。

- 工作目录：仓库根目录。
- 运行时依赖只允许 `numpy`、`Pillow`、`rapidocr_onnxruntime`；新增依赖前先说明理由。
- 平台：Windows 10/11；Python 3.10+。
- 识别资产由 `tools/` 下的脚本生成，不手工编辑生成物。

## 常用命令

```powershell
python -m unittest discover -s tests -t .
python tools/validate_cases.py --strict
python tools/run_accuracy.py --strict
python -m tools.live_recognize --replay samples/frames/draft_001
```

如果本机没有 `python`，使用项目 `启动助手.bat` 里配置的 Python。

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
- 先写失败测试，再实现；提交保持小而可回滚。

## 提交前

```powershell
git diff --check
python -m unittest discover -s tests -t .
python tools/validate_cases.py --strict
```

涉及识别参数时再加 `python tools/run_accuracy.py --strict`。文档使用中文；用户可见文案也用
中文，技术标识符保持英文。
