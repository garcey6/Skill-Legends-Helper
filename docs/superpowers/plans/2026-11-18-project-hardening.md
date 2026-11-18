# Project Hardening Implementation Plan

> **For agentic workers:** Use the `executing-plans` workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the highest-ROI items from the 2026-11-18 project-improvement report without changing recognition behavior: governance, repo-local AI skills, accuracy regression, and CI.

**Architecture:** Add repository metadata and automation around the existing offline Python/Tk app. The only runtime code change is a read-only accuracy harness that reuses `tools/live_recognize.run_image`; recognition assets and thresholds stay untouched.

**Tech Stack:** Python 3.10+, unittest, GitHub Actions, Markdown, python-docx report as the requirement source.

**Requirement source:** `D:\EdgeDownload\Skill-Legends-Helper项目改进建议报告.docx`

## Global Constraints

- Do not change recognition thresholds, scoring weights, or runtime data.
- Keep `requirements.txt` at its current three runtime dependencies.
- Keep all commands runnable on Windows PowerShell and GitHub Actions `windows-latest`.
- New skills live in `.agents/skills/<name>/SKILL.md` with `name` and `description` frontmatter.
- Current test command: `python -m unittest discover -s tests -t .`.
- Current validation command: `python tools/validate_cases.py --strict`.

## Review Focus

- A new clone can identify the license, risk, and contribution path without opening X.
- A contributor can run tests and accuracy regression with the documented commands.
- A 1–5 hero frame still yields the same slots; accuracy failure is surfaced, never silently ignored.
- Skill files are discoverable by name and do not instruct users to edit generated templates by hand.
- CI runs the same commands as local development and does not require a game window.

---

### Task 1: Repository governance and safety

**Files:**
- Create: `LICENSE`
- Create: `CHANGELOG.md`
- Create: `docs/RISK.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Modify: `README.md` risk section

- [ ] Add MIT license, changelog, risk document, and issue forms.
- [ ] Link the risk document from README.
- [ ] Run `git diff --check`.
- [ ] Commit.

### Task 2: Repo-local AI skills

**Files:**
- Create: `AGENTS.md`
- Create: `.agents/skills/recognition-templates/SKILL.md`
- Create: `.agents/skills/guide-kb/SKILL.md`
- Create: `.agents/skills/ocr-glyphs/SKILL.md`
- Create: `.agents/skills/data-rebuild/SKILL.md`
- Create: `.agents/skills/release-replay/SKILL.md`
- Create: `tests/test_repo_hygiene.py`

- [ ] Write the five skill files with frontmatter, trigger, workflow, and acceptance checks.
- [ ] Write a test that discovers exactly the five expected skills and frontmatter fields.
- [ ] Run the test and full unittest suite.
- [ ] Commit.

### Task 3: Accuracy regression harness and CI

**Files:**
- Create: `tools/run_accuracy.py`
- Create: `tests/test_accuracy.py`
- Create: `.github/workflows/ci.yml`
- Create: `.github/pull_request_template.md`
- Modify: `docs/DEVELOPMENT.md`

- [ ] Write `compute_metrics()` and its failing test.
- [ ] Implement the metrics: slot accuracy, name accuracy, exact-case rate, P50/P95 latency.
- [ ] Add CLI flags `--meta`, `--strict`, `--out`.
- [ ] Add a test that current validation cases pass.
- [ ] Add GitHub Actions Windows workflow: install requirements, unittest, validate cases, accuracy.
- [ ] Document local commands.
- [ ] Run full suite and accuracy.
- [ ] Commit.

### Task 4: Release follow-up plan

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] Add the deferred report items: resolution-bucket metadata, larger holdout set, PyInstaller release package.
- [ ] Commit.

## Deferred in this pass

- 3.2 multi-resolution template buckets (requires an asset-layout change and new real frames).
- 3.3 target 50–100 holdout frames (needs more user-supplied screenshots).
- PyInstaller/EXE release (needs a Windows packaging build and signing policy).
