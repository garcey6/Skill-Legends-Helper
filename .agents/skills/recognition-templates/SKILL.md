---
name: recognition-templates
description: 维护 data/recognize/layout.json、流派色度模板与白色符文模板；当 UI 改版、分辨率变化、流派误判或需要新增验证截图时使用。
---

# 识别模板维护

## 触发条件

- 游戏 UI 改版，名单位置、底部流派图标或右侧面板发生变化。
- 不同分辨率下色度匹配偏移，或 `suspect_slots` / `null` 明显增多。
- 新增真实截图，需要扩展回放或验证夹具。

## 先看什么

1. `data/recognize/layout.json`：`rois.icons`、`rois.nameplates`、`reference_width`、
   `margin_min`、`stability`。当前名单位置是 `[0.02, 0.98, 0.35, 0.62]`，覆盖最多 5 个
   英雄。
2. `app/vision/schools.py`：色度距离、匈牙利分配、白色符文 NCC 决胜。
3. `tools/preview_draft.py`：快速把一张截图跑成可视化预览。
4. `tools/calibrate_thresholds.py`：用验证集观察阈值变化，不要凭感觉改。

## 工作流

1. 把新截图放到 `samples/validation/` 或 `samples/frames/`，不要覆盖旧夹具。
2. 用 `python tools/validate_cases.py` 跑基线，记录槽位、流派和可疑槽位。
3. 只改布局/模板生成参数；模板由脚本重建：
   ```powershell
   python tools/build_templates.py
   python tools/build_school_templates.py
   python tools/build_school_runes.py
   ```
4. 用 `python tools/preview_draft.py --image <截图>` 检查框选和读数。
5. 跑 `python tools/validate_cases.py --strict` 与 `python tools/run_accuracy.py --strict`。
6. 如果阈值确实需要调整，附 before/after 的准确率与延迟，不要只贴一张“看起来对了”的图。

## 验收清单

- [ ] 1、3、5 个英雄的截图都能按槽位输出，不压缩、不补造第 3 个。
- [ ] 名单位置含“特权解锁/随机”时停止，不把特殊牌当英雄。
- [ ] 未知槽位保持 `null`，不猜名字。
- [ ] `validate_cases --strict` 与 `run_accuracy --strict` 通过。
- [ ] 不手工修改 `schools_chroma.json`、`school_runes.json`；它们由 build 脚本生成。

## 风险

- 只改一个分辨率的模板可能让另一个分辨率回归；至少保留一条旧夹具做反向验证。
- 不要把 `margin_min` 调到能“全过”验证集却对未知流派过度自信。
