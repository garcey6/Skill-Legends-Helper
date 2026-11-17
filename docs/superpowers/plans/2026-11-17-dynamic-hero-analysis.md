# 动态英雄数与全英雄分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 识别顶部实际出现的英雄数（1~5），在浮窗中列出每个英雄的完整方案；把四个 bat 收敛成一个菜单入口。

**Architecture:** 保留现有 ROI + RapidOCR/字模链路，只把固定的 3 槽改为按石质名牌数量和“特权解锁/随机”边界动态生成候选。浮窗渲染从“第一名详情 + 备选名字”改为“每个英雄一个完整区块”，卡片按英雄数增高，超过屏幕工作区时进入滚动视口。启动器合并为一个菜单式 `启动助手.bat`，删除三个旧 bat。

**Tech Stack:** Python 3.10+、Tkinter、Pillow、RapidOCR（rapidocr_onnxruntime）、unittest、Windows batch。

**Spec:** `docs/superpowers/specs/2026-11-17-dynamic-hero-analysis-design.md`

## Global Constraints

- 英雄数量上限 5；不实现第 6 个及以上的布局。
- 不改 `Advisor.score_hero` / `recommend` 的评分权重、核心卡排序和攻略检索。
- 自动层抓帧前必须隐藏浮窗；扩大名牌 ROI 后仍不能把浮窗截进结果。
- 英雄槽位保持屏幕顺序；未识别的英雄保留 `None` 占位，不压缩。
- 浮窗宽度保持 620；文字不缩小硬塞，超过工作区用滚动。
- 本次不改网页手动上传的旧 `app/vision/recognizer.py` 路径。
- 不新增运行时依赖。

## Review Focus

- 顶部只有 1 个英雄时，自动层仍应显示结果，而不是被 `hero_names < 2` 拦截。
- 第 4/5 个名牌被浮窗、鼠标或裁切遮住时，不能把“特权解锁/随机”当英雄，也不能强行补到 3 个。
- OCR 把 `特权解锁` 误读成近似文本时，特殊词表必须优先于英雄名校正。
- 5 个英雄时浮窗高度超过工作区：滚轮必须能滚到最后一个英雄，拖动仍只移动浮窗。
- 统一菜单的 1/2/3/4 分支必须分别启动浮窗、网页、设置、退出；旧 bat 删除后文档不能再引用它们。

---

## File Structure

- `data/recognize/layout.json`：名牌 ROI 扩到 `x=0.02..0.98`。
- `app/vision/ocr.py`：动态名牌检测、特殊名牌结束、动态候选、OCR 失败槽位。
- `app/vision/glyphs.py`：字模兜底动态候选，不再补齐 3。
- `app/vision/pipeline.py`：动态候选的 warnings 与透传；不加固定数量。
- `agent.py`：允许 1 个英雄；按候选实际数量提示缺失。
- `app/overlay/hud.py`：多英雄区块渲染、动态高度、滚动视口。
- `启动助手.bat`：唯一入口菜单；删除 `启动浮窗.bat`、`启动网页版.bat`、`打开设置.bat`。
- `tests/test_dynamic_heroes.py`：OCR/字模动态候选。
- `tests/test_hud_multi.py`：1/3/5 英雄渲染。
- `tests/test_hud_scroll.py`：滚动视口裁剪。
- `tests/test_launcher.py`：唯一 bat 和菜单内容。
- README、INSTALL、USER_GUIDE、TROUBLESHOOTING、网站版教程：入口说明更新。

---

### Task 1: 动态 OCR 与字模候选

**Files:**
- Modify: `app/vision/ocr.py:71-218`
- Modify: `app/vision/glyphs.py:138-160`
- Modify: `data/recognize/layout.json`
- Test: `tests/test_dynamic_heroes.py`

**Interfaces:**
- Consumes: 现有 `RapidOcrNameMatcher`、`GlyphMatcher` 和 `nameplates` ROI。
- Produces:
  - `RapidOcrNameMatcher.detect_plates(arr: np.ndarray, client_w: int) -> List[Tuple[int,int,int,int]]`，返回最多 5 个。
  - `RapidOcrNameMatcher.match(nameplates, client_w, glyph_matcher) -> dict`，`candidates` 长度为实际英雄数，`0..5`。
  - `GlyphMatcher.match(arr, groups) -> dict`，`candidates` 长度等于 `min(len(groups), 5)`，不再补 3。
  - `layout.rois.nameplates = [0.02, 0.98, 0.35, 0.62]`。

- [ ] **Step 1: 写动态候选失败测试**

```python
# tests/test_dynamic_heroes.py
import json
import unittest
from pathlib import Path

import numpy as np

from app.vision.glyphs import GlyphMatcher
from app.vision.ocr import RapidOcrNameMatcher

NAMES = ["森林游侠", "神秘法师", "魔镜", "守财奴", "狂暴战将", "精灵牧师"]


class FakeGlyph:
    def match(self, arr, groups):
        return {"candidates": []}


class FakeOcr(RapidOcrNameMatcher):
    def __init__(self, texts):
        super().__init__(NAMES)
        self.texts = list(texts)

    @property
    def available(self):
        return True

    @property
    def error(self):
        return ""

    def detect_plates(self, arr, client_w):
        return [(0, 0, 80, 40)] * len(self.texts)

    def _ocr_crop(self, crop):
        return self.texts.pop(0) if self.texts else ("", 0.0)


def names_for(texts):
    result = FakeOcr(texts).match(np.zeros((80, 400, 3), np.uint8), 1800, FakeGlyph())
    return [c["name"] for c in result["candidates"]]
```

把断言放进 `class DynamicHeroTest(unittest.TestCase)`，`names_for` 作为模块级辅助函数。

测试断言：

```python
def test_three_heroes_stop_at_special(self):
    self.assertEqual(
        names_for([
            ("森林游侠", .99), ("神秘法师", .99), ("魔镜", .99),
            ("特权解锁", .99), ("随机", .99),
        ]),
        ["森林游侠", "神秘法师", "魔镜"],
    )

def test_four_heroes(self):
    self.assertEqual(
        names_for([
            ("森林游侠", .99), ("神秘法师", .99), ("魔镜", .99), ("守财奴", .99),
            ("特权解锁", .99),
        ]),
        ["森林游侠", "神秘法师", "魔镜", "守财奴"],
    )

def test_ocr_failure_keeps_slot(self):
    self.assertEqual(
        names_for([("森林游侠", .99), ("", 0.0), ("魔镜", .99), ("随机", .99)]),
        ["森林游侠", None, "魔镜"],
    )

def test_misread_special_plate_stops(self):
    self.assertEqual(
        names_for([("森林游侠", .99), ("特权解", .99), ("随机", .99)]),
        ["森林游侠"],
    )
```

另测 `GlyphMatcher.match` 收到 4 个 group 时返回 4 个候选，不补第 5 个；用真实的 `data/recognize/glyphs.json` 构造 4 个单字 group，断言 `len(result["candidates"]) == 4`。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_dynamic_heroes -v
```

Expected: FAIL，因为当前只返回 3 个候选，且 `特权解锁` 会被当成额外槽。

- [ ] **Step 3: 实现动态检测与候选**

在 `app/vision/ocr.py` 增加：

```python
MAX_HEROES = 5

def _is_special_plate(text: str) -> bool:
    text = _normalize_text(text)
    return any(token in text for token in ("特权", "解锁", "随机"))
```

`detect_plates` 不再 `return boxes[:3]`，改为 `return boxes[:MAX_HEROES]`。

`match`：

- `candidates: List[Optional[Dict[str, Any]]] = []`
- 遍历 `plates[:MAX_HEROES]`：
  - OCR 得到 `text, confidence`
  - `if _is_special_plate(text): break`
  - 追加一个候选，name 可以是 `None`
- OCR 候选有缺失时，调用字模；只为已有索引填充，不从字模追加超过 OCR 英雄边界的槽。
- 如果 OCR 一个名牌都没有检测到，才使用字模的完整候选列表。
- 删除所有 `[:3]` 和 `for index in range(3)`。

`GlyphMatcher.match` 删除补齐 3 的循环，改为遍历 `groups[:5]`。

- [ ] **Step 4: 扩大名牌 ROI**

把 `data/recognize/layout.json` 的：

```json
"nameplates": [0.02, 0.62, 0.35, 0.62]
```

改为：

```json
"nameplates": [0.02, 0.98, 0.35, 0.62]
```

- [ ] **Step 5: 运行测试**

Run:

```powershell
python -m unittest tests.test_dynamic_heroes tests.test_ocr tests.test_live -v
```

Expected: PASS；现有 3 英雄夹具仍返回 3。

- [ ] **Step 6: 提交**

```powershell
git add app/vision/ocr.py app/vision/glyphs.py data/recognize/layout.json tests/test_dynamic_heroes.py
git commit -m "feat: recognize dynamic hero count up to five"
```

---

### Task 2: 全英雄浮窗区块

**Files:**
- Modify: `app/overlay/hud.py:241-370`
- Test: `tests/test_hud_multi.py`

**Interfaces:**
- Consumes: `render_result(result, meta, warning, capture_key, toggle_key, quit_key) -> Image.Image`。
- Produces:
  - `render_result` 仍返回 Pillow Image，宽度恒为 `WIDTH=620`，高度随 `len(recommendations)` 增长。
  - 新增内部 `_render_hero_section(draw, image, card, y, index) -> int`。
  - 每个卡片区块包含：头像、名字、评级、分数、`首选/第 N` 标签、定位/路线、理由、3 张核心卡、开局、天赋/大招图标（有数据时）。

- [ ] **Step 1: 写多英雄渲染失败测试**

```python
# tests/test_hud_multi.py
def _card(name, score):
    return {
        "name": name, "score": score, "tier": "S", "role": "法师",
        "reasons": ["开放流派契合", "核心卡可叠加"],
        "core_cards": [{"name": "先发制人", "rarity": 3, "desc": "开局加攻"}],
        "build": {"schools": ["大招流", "精灵流"], "steps": ["前 3 回合补生存"]},
        "has_guide": True,
    }

def _render(n):
    result = {"recommendations": [_card("英雄%d" % i, 90 - i) for i in range(n)],
              "draft": {"enabled": [], "banned": []}}
    return render_result(result)
```

断言：

```python
assert _render(1).width == 620
assert _render(3).height > _render(1).height
assert _render(5).height > _render(3).height
assert _render(5).height > 1200
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_hud_multi -v
```

Expected: FAIL，因为当前高度固定 560，且只渲染第一名。

- [ ] **Step 3: 实现多英雄布局**

在 `hud.py` 增加常量：

```python
HEADER_H = 150
SECTION_H = 190
SCHOOLS_H = 150
FOOTER_H = 30
```

`render_result` 计算：

```python
height = HEADER_H + SECTION_H * len(cards) + SCHOOLS_H + FOOTER_H + 12
image = Image.new("RGB", (WIDTH, height), BG)
```

按顺序渲染每个 card；第一张显示 `首选`，其余显示 `第 2`、`第 3`…；每块都渲染完整信息，不只名字/分数。

最后按 `y = HEADER_H + SECTION_H * len(cards) + 8` 渲染启用/禁用流派和页脚。

- [ ] **Step 4: 运行渲染测试**

Run:

```powershell
python -m unittest tests.test_hud_multi -v
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add app/overlay/hud.py tests/test_hud_multi.py
git commit -m "feat: render every hero in the floating analysis"
```

---

### Task 3: 超高浮窗滚动视口

**Files:**
- Modify: `app/overlay/hud.py:373-517`
- Test: `tests/test_hud_scroll.py`

**Interfaces:**
- Consumes: `Hud.show(image, game_hwnd)` 现在可接收任意高度图片。
- Produces:
  - 纯函数 `viewport_crop(image: Image.Image, offset: int, max_height: int) -> Tuple[Image.Image, int]`，返回裁剪图和新的 offset。
  - `Hud._scroll_offset: int`、`Hud._full_image: Optional[Image.Image]`、`Hud._viewport_height: int`。
  - 鼠标滚轮事件 `Hud._on_mousewheel(event)`。

- [ ] **Step 1: 写视口裁剪测试**

```python
# tests/test_hud_scroll.py
def test_viewport_crop_clamps():
    image = Image.new("RGB", (100, 1000), "black")
    view, offset = viewport_crop(image, 0, 300)
    assert view.height == 300 and offset == 0
    view, offset = viewport_crop(image, 900, 300)
    assert view.height == 300 and offset == 700
    view, offset = viewport_crop(image, -50, 300)
    assert offset == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_hud_scroll -v
```

Expected: FAIL，`viewport_crop` 不存在。

- [ ] **Step 3: 实现滚动视口**

- 增加 `viewport_crop`。
- `Hud.show`：
  - 保留 `last_source` 为完整图片；
  - 计算 `max_height = monitor_work_area 高度 - 40`；
  - `viewport_height = min(full.height, max_height)`；
  - 如果完整高度超过视口，设置 `self._scroll_offset = 0`；
  - 调用 `_render_viewport`。
- `Hud._render_viewport` 用 `viewport_crop` 生成裁剪图、更新 canvas/geometry；`self.last_image` 是当前视口图。
- 绑定 `<MouseWheel>`：向上 delta>0 减 offset，向下加 offset，步长 60；调用 `_render_viewport`。
- 当完整高度超过视口时，在视口右下角绘制一条淡提示「滚轮查看全部」；不滚动时不显示。
- `_place` 使用视口图尺寸；保存位置逻辑不变；拖动仍作用于整个窗口。
- 不滚动时保持原来的显示尺寸和行为。

- [ ] **Step 4: 运行滚动测试**

Run:

```powershell
python -m unittest tests.test_hud_scroll -v
```

Expected: PASS。

- [ ] **Step 5: 手工检查**

启动浮窗，用 5 个英雄的合成 `recommendations` 或临时数据确认：

- 卡片高度限制在工作区；
- 滚轮能滚到最后一个英雄；
- 按住卡片拖动仍然是移动窗口，不滚动内容。

- [ ] **Step 6: 提交**

```powershell
git add app/overlay/hud.py tests/test_hud_scroll.py
git commit -m "feat: scroll tall multi-hero overlay"
```

---

### Task 4: 允许 1 个英雄 + 统一启动入口

**Files:**
- Modify: `agent.py:319-352`
- Create: `启动助手.bat`
- Delete: `启动浮窗.bat`, `启动网页版.bat`, `打开设置.bat`
- Modify: `README.md`, `docs/INSTALL.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md`, `docs/网站版与浮窗助手版完整教程.md`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: `Agent._handle_live` 接收动态 `candidates`；现有 Python 查找逻辑。
- Produces:
  - `Agent._handle_live` 在 `hero_names` 非空时显示结果；warning 根据 `candidates` 中 `None` 数量生成。
  - `启动助手.bat` 菜单：`1` 浮窗+网页，`2` 仅网页，`3` 设置，`4` 退出。

- [ ] **Step 1: 写入口与 1 英雄测试**

```python
# tests/test_launcher.py
ROOT = Path(__file__).resolve().parent.parent

def test_only_one_launcher():
    assert (ROOT / "启动助手.bat").exists()
    assert not (ROOT / "启动浮窗.bat").exists()
    assert not (ROOT / "启动网页版.bat").exists()
    assert not (ROOT / "打开设置.bat").exists()

def test_launcher_has_menu():
    text = (ROOT / "启动助手.bat").read_text(encoding="utf-8")
    for token in ("agent.py", "run.py", "http://127.0.0.1:8777", "choice"):
        assert token in text
```

另加一个纯函数测试（在 `agent.py` 抽出）：

```python
def test_hero_warning_for_one_hero():
    assert agent.hero_warning([{"name": "森林游侠"}]) == ""
    assert "1" in agent.hero_warning([{"name": None}])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: FAIL，旧 bat 仍存在、`hero_warning` 不存在。

- [ ] **Step 3: 改 Agent 动态英雄数**

- 在 `agent.py` 增加纯函数：

```python
def hero_warning(candidates: List[Dict[str, Any]]) -> str:
    missing = sum(1 for c in candidates if not c.get("name"))
    return "有 %d 个英雄未识别" % missing if missing else ""
```

- `_handle_live`：把 `len(hero_names) < 2` 改为 `if not hero_names: return`。
- `warning = hero_warning(candidates)`。
- 日志继续输出所有已识别英雄。

- [ ] **Step 4: 写唯一启动器**

`启动助手.bat` 复用原 `启动浮窗.bat` 的 Python 查找逻辑，然后：

```bat
:menu
echo.
echo  选技大乱斗 - 浮窗助手
echo  1. 启动浮窗 + 网页（默认）
echo  2. 只启动网页
echo  3. 打开设置
echo  4. 退出
choice /c 1234 /n /m "请选择 [1-4]: "
if errorlevel 4 goto end
if errorlevel 3 goto settings
if errorlevel 2 goto web
goto overlay

:overlay
"%PYTHON_EXE%" %PYTHON_ARGS% agent.py --port 8777
goto end

:web
"%PYTHON_EXE%" %PYTHON_ARGS% run.py --port 8777
goto end

:settings
set "URL=http://127.0.0.1:8777"
if exist "data\server_url.txt" set /p URL=<"data\server_url.txt"
start "" "%URL%"
goto end

:end
if not defined XUANJI_NO_PAUSE pause
endlocal
```

删除三个旧 bat。

- [ ] **Step 5: 更新文档入口**

把所有 `启动浮窗.bat`、`启动网页版.bat`、`打开设置.bat` 的说法改成：

```text
双击 启动助手.bat，选择 1/2/3。
```

至少覆盖 README、INSTALL、USER_GUIDE、TROUBLESHOOTING、网站版教程。

- [ ] **Step 6: 运行测试**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add agent.py 启动助手.bat README.md docs/INSTALL.md docs/USER_GUIDE.md docs/TROUBLESHOOTING.md docs/网站版与浮窗助手版完整教程.md tests/test_launcher.py
git rm 启动浮窗.bat 启动网页版.bat 打开设置.bat
git commit -m "feat: unify launcher and allow one-hero drafts"
```

---

### Task 5: 全量回归与真实画面验证

**Files:**
- Modify: `docs/live-perf.md` only if measured behavior changes.
- No production code beyond fixes found here.

- [ ] **Step 1: 运行全部单元测试**

Run:

```powershell
python -m unittest discover -s tests -t . -v
```

Expected: PASS，新增测试全部通过。

- [ ] **Step 2: 回放现有验证帧**

Run:

```powershell
python -m tools.live_recognize --replay samples/frames/draft_001 --pretty
python -m tools.live_recognize --replay samples/frames/draft_002 --pretty
python tools/validate_cases.py --strict
```

Expected：两段回放仍为 3 英雄 / 8 启用 / 5 禁用；验证集英雄 3/3。

- [ ] **Step 3: 人工检查 3 英雄与 5 英雄浮窗**

- 用现有 3 英雄帧启动浮窗，确认 3 个完整区块、无滚动。
- 用临时构造的 5 个 `recommendations` 检查浮窗：可滚到第 5 个英雄；拖动仍移动窗口。
- 双击 `启动助手.bat`，分别检查菜单 1、2、3、4。

- [ ] **Step 4: 检查没有残留旧入口**

Run:

```powershell
Get-ChildItem *.bat
Select-String -Path README.md,docs\*.md -Pattern '启动浮窗.bat|启动网页版.bat|打开设置.bat'
```

Expected：只剩 `启动助手.bat`；文档无旧入口引用。

- [ ] **Step 5: 提交修复（如有）并推送**

```powershell
git status --short
git add -A
git commit -m "test: verify dynamic hero analysis and launcher"
git push origin main
```
