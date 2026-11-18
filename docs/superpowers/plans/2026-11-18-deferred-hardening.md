# 暂缓项实现计划：模板分组、真实帧 holdout、免安装发行包

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `docs/ROADMAP.md` 中“质量与发版”的三项暂缓能力做成可运行、可测试、可验收的代码：多分辨率模板分组、真实帧 holdout 导入/门禁、PyInstaller 免安装包。

**Architecture:** 三个互相独立的交付，按任务顺序实现，每个任务单独提交。模板分组通过 `data/recognize/layout.json` 的 `reference_resolution` + `template_groups` 描述档位，运行时用 `AssetCache` 按客户区宽度选择并缓存匹配器；holdout 用独立导入工具维护 `samples/validation/holdout/meta.json`，`run_accuracy.py` 增加最小案例数门禁；发行包用 `tools/build_release.py` 生成 one-folder PyInstaller 产物、版本清单和 SHA256 校验文件。

**Tech Stack:** Python 3.10+、numpy、Pillow、RapidOCR（可选但发行包应包含）、PyInstaller（仅构建依赖）、unittest。

**Spec:** `docs/ROADMAP.md` 的“质量与发版”章节；既有约定见 `AGENTS.md`、`docs/DEVELOPMENT.md`。

## Global Constraints

- 运行时依赖只允许 `numpy`、`Pillow`、`rapidocr_onnxruntime`；PyInstaller 只能进 `requirements-build.txt`，不能进 `requirements.txt`。
- 不改变评分权重、流派阈值或识别算法核心；本计划只增加模板选择、数据导入和打包能力。
- 浮窗宽度保持 620；真实帧截图不能裁切、不能把浮窗截进去。
- 用户可见文案和文档用中文；技术标识符保持英文。
- 先写失败测试，再实现；每个任务结束前跑全量测试、`validate_cases.py --strict` 和 `run_accuracy.py --strict`。
- 不提交 `data/settings.json`、`data/server_url.txt`、`data/captures/`、`data/uploads/`、`data/source/`、`dist/`、`build/`、`*.zip`、`release.json`。
- 真实帧 holdout 的 50–100 组数据必须来自真实游戏窗口，不能用合成图冒充；本计划交付导入工具与门禁，数据由使用者按 `docs/HOLDOUT.md` 补齐。

## Review Focus

- 宽度正好等于分组边界（1919/1920、2559/2560）时只能命中一个分组。
- 分组文件缺失或 JSON 损坏时，加载失败要给出可定位的路径，不能静默退回错误模板。
- 导入 holdout 时未知英雄、重复案例名、非 RGB/超大图片不能让 `meta.json` 变成半写状态。
- 真实帧少于门禁数量时 `--min-cases` 必须失败；没有标注的图片不能被算作通过。
- 冻结后的 exe 必须能从自身目录找到 `data/` 与 `static/`，且构建清单不能把 `settings.json`、上传目录或原始数据表打进去。

---

### Task 1: 多分辨率模板分组

**Files:**
- Modify: `data/recognize/layout.json`
- Create: `app/vision/assets.py`
- Modify: `app/live/sampler.py`
- Modify: `agent.py`
- Modify: `tools/live_recognize.py`
- Test: `tests/test_template_groups.py`

**Interfaces:**
- Consumes: `data/recognize/{layout,schools_chroma,school_runes,glyphs}.json`；`SchoolMatcher`、`GlyphMatcher`、`RapidOcrNameMatcher`。
- Produces:
  - `TemplateGroup` frozen dataclass：`id: str`、`min_width: int`、`max_width: Optional[int]`、`reference_width: int`、`schools: str`、`runes: str`、`glyphs: str`；方法 `contains(width: int) -> bool`、`to_dict() -> dict`。
  - `select_template_group(layout: Mapping[str, Any], client_width: int) -> TemplateGroup`。
  - `missing_template_files(layout: Mapping[str, Any], base_dir: Path) -> list[str]`。
  - `AssetBundle` dataclass：`group`、`school_matcher`、`glyph_matcher`、`ocr_matcher`。
  - `AssetCache(layout, base_dir, names, use_ocr=True)`；方法 `for_width(client_width: int) -> AssetBundle`，同一分组只构建一次。
  - `LiveSampler(..., asset_provider: Optional[Callable[[int], Any]] = None)`；当宽度跨组时替换匹配器，不阻塞识别线程。

- [ ] **Step 1: Write the failing test**

创建 `tests/test_template_groups.py`，至少包含：

```python
LAYOUT = json.loads((ROOT / "data" / "recognize" / "layout.json").read_text(encoding="utf-8"))

class TemplateGroupSelectionTest(unittest.TestCase):
    def test_reference_resolution_is_recorded(self):
        self.assertEqual(LAYOUT["reference_resolution"]["width"], 1800)
        self.assertEqual(LAYOUT["reference_resolution"]["height"], 1118)

    def test_widths_select_exactly_one_group(self):
        cases = [(1280, "hd"), (1919, "hd"), (1920, "fhd"),
                 (2559, "fhd"), (2560, "qhd"), (3840, "qhd")]
        for width, expected in cases:
            with self.subTest(width=width):
                self.assertEqual(select_template_group(LAYOUT, width).id, expected)

    def test_groups_cover_every_width_once(self):
        for width in range(1, 4001):
            hits = [g for g in LAYOUT["template_groups"] if g["min_width"] <= width and (g["max_width"] is None or width <= g["max_width"])]
            self.assertEqual(len(hits), 1, width)

    def test_group_files_exist(self):
        self.assertEqual(missing_template_files(LAYOUT, ROOT / "data" / "recognize"), [])
```

再加 `AssetCacheTest`：

```python
def test_cache_reuses_bundle_and_reports_group(self):
    cache = AssetCache(LAYOUT, ROOT / "data" / "recognize", ["神秘法师"], use_ocr=False)
    first = cache.for_width(1920)
    second = cache.for_width(2000)
    self.assertIs(first, second)
    self.assertEqual(first.group.id, "fhd")
    self.assertEqual(cache.for_width(2560).group.id, "qhd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_template_groups -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.vision.assets'` 或缺少 `reference_resolution`。

- [ ] **Step 3: Add layout metadata and implement `app/vision/assets.py`**

`data/recognize/layout.json` 增加：

```json
"reference_resolution": {"width": 1800, "height": 1118},
"template_groups": [
  {"id": "hd", "min_width": 0, "max_width": 1919, "reference_width": 1800,
   "schools": "schools_chroma.json", "runes": "school_runes.json", "glyphs": "glyphs.json"},
  {"id": "fhd", "min_width": 1920, "max_width": 2559, "reference_width": 1800,
   "schools": "schools_chroma.json", "runes": "school_runes.json", "glyphs": "glyphs.json"},
  {"id": "qhd", "min_width": 2560, "max_width": null, "reference_width": 1800,
   "schools": "schools_chroma.json", "runes": "school_runes.json", "glyphs": "glyphs.json"}
]
```

三个档位当前共用同一套模板；以后新增 `schools_chroma_qhd.json` 等文件时只改对应 `schools/runes/glyphs` 路径。`select_template_group` 对空分组或宽度为空时退回 `reference_resolution.width`，对没有命中的宽度抛出 `ValueError("no template group covers %dpx" % client_width)`。`missing_template_files` 返回不存在的 `base_dir/相对路径` 字符串列表。

`AssetCache` 从分组路径读取 JSON，构建 `SchoolMatcher`（带 runes）、`GlyphMatcher`，OCR 只构建一次并在分组间共享；缓存键是 `group.id`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_template_groups -v`
Expected: PASS。

- [ ] **Step 5: Integrate runtime selection**

`app/live/sampler.py` 增加可选 `asset_provider`：在 `_capture_loop` 拿到 `state.client_w` 后调用 `bundle = self.asset_provider(width)`；若 `bundle is not self._assets`，更新 `self.school_matcher/glyph_matcher/ocr_matcher` 并记录 `self._assets`。`agent.py` 用 `AssetCache` 初始化初始 bundle（按 `layout["reference_resolution"]["width"]`），把 `cache.for_width` 传给 sampler；`tools/live_recognize.load_assets(width: Optional[int] = None)` 用 `select_template_group` 选择分组，返回 `"template_group": group.to_dict()`。

在 `tests/test_sampler.py` 增加一个使用 fake provider 的断言：第一次抓帧后 `sampler._assets.group.id` 为 `fhd`，宽度跨到 `qhd` 后 `_assets` 改变且旧 matcher 不再被使用。测试用现有 fake source，不启动真实线程；直接调用内部选择方法或捕获循环的一帧均可，保持确定性。

- [ ] **Step 6: Run affected tests and commit**

Run: `python -m unittest tests.test_template_groups tests.test_sampler tests.test_live -v`
Expected: PASS。

```bash
git add data/recognize/layout.json app/vision/assets.py app/live/sampler.py agent.py tools/live_recognize.py tests/test_template_groups.py tests/test_sampler.py
git commit -m "feat: select recognition templates by resolution group"
```

---

### Task 2: 真实帧 holdout 导入与最小案例门禁

**Files:**
- Create: `tools/import_validation.py`
- Create: `tests/test_validation_import.py`
- Create: `samples/validation/holdout/README.md`
- Create: `docs/HOLDOUT.md`
- Modify: `tools/run_accuracy.py`
- Modify: `tests/test_accuracy.py`
- Modify: `README.md`、`docs/DEVELOPMENT.md`

**Interfaces:**
- Consumes: `samples/validation/meta.json` 的结构、`Advisor` 的英雄/流派闭集。
- Produces:
  - `normalize_heroes(values: Sequence[str], advisor: Any) -> list[str]`：接受正式名或别名，返回正式名；未知名称抛 `ValueError`。
  - `normalize_schools(values: Sequence[str], advisor: Any) -> list[str]`：校验 13 流派。
  - `import_case(image: Path, name: str, heroes: Sequence[str], schools: Optional[Sequence[str]], note: str, dataset: Path, replace: bool = False, advisor: Any = None) -> dict`：复制为 `dataset/<name>.png`，更新 `dataset/meta.json`，返回新案例。
  - `strict_failure(metrics: Mapping[str, Any], min_cases: int = 0) -> bool`。
  - `run_accuracy.py --min-cases N`：`--strict` 时案例数少于 N 也返回 1。

- [ ] **Step 1: Write the failing tests**

`tests/test_validation_import.py` 用 `tempfile.TemporaryDirectory()` 和 Pillow 生成 `800x450` RGB 图片，断言：

```python
def test_import_case_copies_image_and_writes_meta(self):
    # 通过真实 Advisor；别名“渣克鼠王”应归一为“渣客鼠王”
    case = import_case(image, "holdout_001", ["渣克鼠王", "神秘法师"], None,
                       "窗口 1920x1080", dataset)
    self.assertEqual(case["client"], "holdout_001.png")
    self.assertEqual(case["expected"]["heroes"], ["渣客鼠王", "神秘法师"])
    self.assertTrue((dataset / "holdout_001.png").is_file())
    meta = json.loads((dataset / "meta.json").read_text(encoding="utf-8"))
    self.assertEqual(len(meta["cases"]), 1)
    self.assertEqual(meta["cases"][0]["resolution"], [800, 450])

def test_duplicate_name_and_unknown_hero_are_rejected(self):
    with self.assertRaises(ValueError):
        import_case(image, "holdout_001", ["神秘法师"], None, "", dataset)
    with self.assertRaises(ValueError):
        import_case(image, "holdout_002", ["不存在的英雄"], None, "", dataset)
```

在 `tests/test_accuracy.py` 增加：

```python
def test_strict_failure_honors_min_cases(self):
    metrics = compute_metrics([{"expected": ["A"], "actual": ["A"], "latency_ms": 1}])
    self.assertFalse(strict_failure(metrics, min_cases=1))
    self.assertTrue(strict_failure(metrics, min_cases=2))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_validation_import tests.test_accuracy -v`
Expected: FAIL，`ImportError: cannot import name 'import_case'` / `strict_failure`。

- [ ] **Step 3: Implement importer and gate**

`tools/import_validation.py`：
- `--image`（可重复）、`--name`、`--heroes`（逗号分隔）、`--schools`（可选，逗号分隔）、`--note`、`--dataset`（默认 `samples/validation/holdout`）、`--replace`。
- 只接受 RGB/RGBA；RGBA 转 RGB；最小 640×360，最大 7680×4320；保存 PNG。
- 先完成所有校验，再写图片和 `meta.json`；写入用临时文件 + `os.replace`，避免半写。
- 新建 `meta.json` 时 `description` 写“真实游戏窗口 holdout；每张图由 tools/import_validation.py 登记”。已有 `description` 保留。
- 案例字段：`name`、`client`、`expected: {heroes, schools}`、`note`、`resolution: [w,h]`、`source`。
- 重复 `name` 且未 `--replace` 时报错；`--replace` 只替换同名案例并覆盖图片。

`tools/run_accuracy.py` 增加 `strict_failure(metrics, min_cases=0)`：`cases == 0`、`cases < min_cases` 或 `failures` 非空都返回 True；CLI 增加 `--min-cases`，默认 0，已有行为不变。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_validation_import tests.test_accuracy -v`
Expected: PASS。

- [ ] **Step 5: Add the real-frame protocol and docs**

`samples/validation/holdout/README.md` 说明目录用途，不提交真实截图前保持为空（可只放 README）。`docs/HOLDOUT.md` 写明：

- 目标 50–100 组；覆盖 1280/1600/1920/2560 宽、窗口化/无边框、不同亮度、1/3/5 英雄、含“特权解锁/随机”边界。
- 截图时先隐藏浮窗（`Alt+X`），保留完整客户区，不要裁切；每张图登记英雄名，流派未知可留 `null`。
- 导入命令：`python tools/import_validation.py --image ... --name ... --heroes "..." --dataset samples/validation/holdout`。
- 验收命令：`python tools/run_accuracy.py --meta samples/validation/holdout/meta.json --strict --min-cases 50`。
- 先补齐 50 组再开 `--min-cases` 门禁；未达到前 CI 仍只跑现有两套基线。

在 `README.md` 的“更多文档”表格加入 `HOLDOUT`；`docs/DEVELOPMENT.md` 的测试段加入导入与门禁命令。

- [ ] **Step 6: Run full verification and commit**

Run: `python -m unittest discover -s tests -t . -v`、`python tools/validate_cases.py --strict`、`python tools/run_accuracy.py --strict`；Expected: 全 PASS/0。

```bash
git add tools/import_validation.py tests/test_validation_import.py samples/validation/holdout/README.md docs/HOLDOUT.md tools/run_accuracy.py tests/test_accuracy.py README.md docs/DEVELOPMENT.md
git commit -m "feat: add real-frame holdout importer and minimum-case gate"
```

---

### Task 3: PyInstaller 免安装发行包

**Files:**
- Create: `tools/build_release.py`
- Create: `tests/test_release.py`
- Create: `requirements-build.txt`
- Create: `docs/RELEASE.md`
- Modify: `.gitignore`、`README.md`、`CHANGELOG.md`、`docs/DEVELOPMENT.md`

**Interfaces:**
- Consumes: `app.__version__`、`agent.py`、`data/`、`static/`。
- Produces:
  - `safe_data_entries(root: Path) -> list[tuple[str, str]]`：返回 PyInstaller `(source, dest)`；只含运行所需数据，排除 `settings.json`、`server_url.txt`、`overlay_position.json`、`meta_stats.json`、`captures/`、`uploads/`、`source/`。
  - `build_command(root: Path, dist: Path, work: Path, ocr: bool = True) -> list[str]`：返回完整 PyInstaller 命令。
  - `sha256_file(path: Path) -> str`。
  - `release_manifest(...) -> dict`：版本、提交、Python、构建时间、exe SHA256、文件数。
  - `zip_release(folder: Path, version: str) -> Path`：生成 `dist/选技助手-<version>-win64.zip` 并写 `.sha256`。
  - CLI：`python tools/build_release.py [--check] [--no-zip] [--allow-no-ocr]`。

- [ ] **Step 1: Write the failing test**

`tests/test_release.py` 用临时目录构造 `data/settings.json`、`data/server_url.txt`、`data/captures/x.png`、`data/source/x.xlsx`、`data/recognize/layout.json`、`static/index.html`，断言：

```python
def test_safe_data_excludes_private_and_source_paths(self):
    entries = safe_data_entries(root)
    joined = "\n".join(src for src, _ in entries)
    self.assertIn("data/recognize/layout.json", joined)
    self.assertIn("static/index.html", joined)
    for bad in ("settings.json", "server_url.txt", "captures", "uploads", "data/source"):
        self.assertNotIn(bad, joined)

def test_build_command_is_one_folder_and_sets_entrypoint(self):
    command = build_command(ROOT, ROOT / "dist", ROOT / "build", ocr=True)
    text = " ".join(command)
    self.assertIn("PyInstaller", text)
    self.assertIn("agent.py", text)
    self.assertIn("--name", text)
    self.assertNotIn("--onefile", text)
    self.assertTrue(any("--collect-all" in part for part in command))
```

再加 `sha256_file` 对临时文件校验、`release_manifest` 含 `version` 与 `sha256`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_release -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'tools.build_release'`。

- [ ] **Step 3: Implement build script and package command**

`tools/build_release.py`：
- `--check` 只打印将打包的条目并检查 `PyInstaller` 是否可用，不构建。
- 未安装 PyInstaller 时打印 `python -m pip install -r requirements-build.txt` 并返回 2。
- `build_command` 使用 `sys.executable -m PyInstaller`，参数：`--noconfirm --clean --console --name 选技助手 --distpath <dist> --workpath <work> --specpath <work> --paths <root>`；每个 `safe_data_entries` 生成 `--add-data "<src>;<dest>"`；`ocr=True` 时加 `--collect-all rapidocr_onnxruntime`，不可用则报错（`--allow-no-ocr` 可跳过并警告）。
- 构建后定位 `dist/选技助手/选技助手.exe`，写 `dist/选技助手/release.json`，压缩整个目录为 `dist/选技助手-<version>-win64.zip`，写同名 `.sha256`。
- `release.json` 的 `commit` 用 `git rev-parse --short HEAD`，失败写 `"unknown"`；`built_at` 用 UTC ISO8601。
- `requirements-build.txt` 只放 `pyinstaller>=6.10`，不混入运行时依赖。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_release -v`
Expected: PASS。

- [ ] **Step 5: Build and smoke-test a one-folder release**

先在临时构建目录安装构建依赖（不写进 `requirements.txt`）：

```powershell
$py = "C:\Users\garcey\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py -m pip install --target "$env:TEMP\xuanji-build" "pyinstaller>=6.10" "rapidocr_onnxruntime>=1.4.4"
$env:PYTHONPATH = "$env:TEMP\xuanji-build"
& $py tools/build_release.py
```

Expected: `dist/选技助手/选技助手.exe`、`dist/选技助手/release.json`、`dist/选技助手-0.1.0-win64.zip` 和 `.sha256` 存在。启动 exe，确认控制台打印“自动识别已开启”、网页端口可访问、`static` 与 `data/guides` 可从包内加载；如无法在本机启动，至少运行 `dist/选技助手/选技助手.exe --help` 确认冻结入口正常。

- [ ] **Step 6: Add release docs and commit**

`docs/RELEASE.md` 写清：构建依赖、命令、产物结构、SHA256 校验、解压到可写目录、SmartScreen 提示、不包含用户设置/截图、卸载即删目录。`.gitignore` 增加 `build/`、`dist/`、`*.zip`。`README.md` 文档表加入 `RELEASE`；`CHANGELOG.md` 的 Unreleased 加入模板分组、holdout、免安装包。`docs/DEVELOPMENT.md` 增加构建命令。

```bash
git add tools/build_release.py tests/test_release.py requirements-build.txt docs/RELEASE.md .gitignore README.md CHANGELOG.md docs/DEVELOPMENT.md
git commit -m "feat: build portable Windows release package"
```

---

## Task Order and Verification

1. Task 1 先完成，确保模板选择不会影响现有识别；跑 `tests.test_template_groups tests.test_sampler tests.test_live`。
2. Task 2 独立于 Task 1；先做导入器，再有真实截图时补 50–100 组并开 `--min-cases 50`。
3. Task 3 独立于前两项；构建产物不入库，只提交脚本和文档。
4. 三项完成后跑：`python -m unittest discover -s tests -t .`、`python tools/validate_cases.py --strict`、`python tools/run_accuracy.py --strict`、`git diff --check`。

## Self-Review

- Spec coverage：模板分组（Task 1）、holdout 扩充工具与门禁（Task 2）、免安装包（Task 3）均有独立任务；50–100 组真实数据明确由使用者补齐，不伪造。
- Step scan：每个任务都有失败测试、失败运行、最小实现、通过运行、提交；没有“适当处理”类空步骤。
- Type consistency：`TemplateGroup`、`select_template_group`、`AssetCache.for_width`、`strict_failure`、`safe_data_entries`、`build_command` 在任务间命名一致。
- Review Focus：边界宽度、缺失模板、重复/未知标签、`--min-cases`、冻结路径与敏感文件排除均有对应测试。
- Proportion：计划只锁定接口、测试和关键值，不写实现细节；真实帧数据不在本计划内生成。
