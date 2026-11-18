---
name: ocr-glyphs
description: 维护英雄名 RapidOCR 闭集校正与 155 字字模兜底；当 OCR 缺字、错字、未知英雄或名称牌变化时使用。
---

# OCR 与字模

## 触发条件

- 英雄名识别错误、缺字、把两个字认成一个字。
- 新英雄加入 60 人闭集，或名称字体/描边变化。
- `glyphs.json` 需要补字模，或 `null` 槽位异常增多。

## 关键事实

- 闭集来自 `app/kb` 的英雄表；OCR 结果只在闭集内校正，**不猜集外名字**。
- 名称牌最多 5 个；遇到 `特权解锁`、`随机` 等特殊牌停止，后面不再当英雄。
- `app/vision/ocr.py` 负责 RapidOCR 与闭集校正；`app/vision/glyphs.py` 负责字模兜底。
- 字模由 `tools/build_glyph_templates.py` 生成；`tools/seed_glyphs_from_samples.py` 可从
  样本补种子。
- 识别不确定时返回 `None`，由上层显示“未识别”并允许手动修正。

## 工作流

1. 先用 `python tools/validate_cases.py` 复现错例，记录期望名与实际名。
2. 若只是缺字模：从真实截图中裁出该字，走 `seed_glyphs_from_samples.py`，再
   `python tools/build_glyph_templates.py`。
3. 若 OCR 把名称切错：检查 `nameplates` ROI 和 OCR 结果边界；只在有证据时调
   `app/vision/ocr.py` 的归一化/校正逻辑。
4. 跑 `python -m unittest tests.test_ocr tests.test_dynamic_heroes -v`。
5. 跑 `python tools/validate_cases.py --strict` 与 `python tools/run_accuracy.py --strict`。

## 验收清单

- [ ] 3 个和 5 个英雄的截图都按槽位输出，不多不少。
- [ ] 特殊牌不被当成英雄。
- [ ] 未知名字返回 `null`，不硬凑成闭集里最像的名字。
- [ ] 新增字模包含真实笔画，不用系统字体直接生成后冒充游戏字模。
- [ ] 不改变 `MAX_HEROES` 和闭集内容，除非任务明确要求。

## 反模式

- 为了让验证集全过而放宽相似度阈值，导致未知英雄被误认。
- 用 OCR 的单个字符结果覆盖整个名称；应当先做整串闭集匹配，再做字模兜底。
