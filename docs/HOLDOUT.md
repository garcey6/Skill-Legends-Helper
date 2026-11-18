# 真实帧 holdout 流程

`tools/run_accuracy.py` 能算准确率，但只有两套固定验证图时，数字只能证明“这两张没坏”。本流程把真实截图持续纳入回归，目标是 50–100 组。

## 1. 采一帧

- 游戏用**无边框窗口**，确认浮窗已隐藏、没有遮挡名牌。
- 截取完整客户区，保存为 PNG；不要裁掉边缘，也不要把桌面截进来。
- 选稳定帧：名牌文字完整、底部流派图标没有动画残影。

## 2. 登记标签

```powershell
python -X utf8 tools/import_validation.py `
  --image "D:\captures\holdout_001.png" `
  --name holdout_001 `
  --heroes "森林游侠,神秘法师,魔镜" `
  --schools "普攻流,大招流" `
  --note "2560x1600 无边框"
```

- `--heroes` 按屏幕从左到右的顺序填写，可以写别名；脚本用 `Advisor` 的闭集转成正式名。
- 未知英雄、重复英雄、未知流派会拒绝导入，避免把错标签写进基线。
- 不确定流派时省略 `--schools`，记为 `null`。
- 同名案例用 `--replace` 显式覆盖。
- 图片和 `meta.json` 都先写临时文件再替换，导入失败不会留下半套案例。

默认目录是 `samples/validation/holdout`，也可以 `--dataset` 指到别处。

## 3. 跑准确率

```powershell
python tools/run_accuracy.py `
  --meta samples/validation/holdout/meta.json `
  --min-cases 50 `
  --strict `
  --out holdout_accuracy.json
```

输出包含：

- `slot_accuracy`：按屏幕槽位对齐，未识别记为错；
- `name_accuracy`：只统计非空期望英雄；
- `exact_case_rate`：整张图英雄序列完全一致；
- `p50_ms` / `p95_ms`：离线识别耗时；不是游戏内端到端延迟；
- `failures`：逐案例期望/实际，便于定位。

`--min-cases 50` 是防回退门槛：样本被删到 50 以下时 `--strict` 必须失败。当前仓库还没有 50 组真实帧，所以这个命令现在会失败；补样本后再把它接进 CI。

## 4. 扩到 50–100 组

建议按下面的桶分配，避免只测一种窗口：

| 维度 | 建议 |
| --- | --- |
| 分辨率 | 1080p 20 组、2K 20 组、4K/超宽 10 组 |
| 英雄数 | 1 人 10 组、2 人 10 组、3 人 20 组、4–5 人 10 组 |
| 流派 | 至少覆盖 8 启用 / 5 禁用各一轮 |
| 亮度 | 亮背景、暗背景各一半 |

新增图片和 `meta.json` 一起提交；不要提交含账号名、聊天窗口或其他个人信息的截图。

## 5. 与固定样例的关系

- `samples/validation/meta.json`：两套固定样例，CI 每次都跑，防止基础能力回退。
- `samples/validation/holdout/meta.json`：真实分布，样本足够后作为更严格的门禁。

两条都使用 `tools/run_accuracy.py`，阈值和指标口径一致。
