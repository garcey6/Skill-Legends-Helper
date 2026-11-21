from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKILLS = {
    "recognition-templates",
    "guide-kb",
    "ocr-glyphs",
    "data-rebuild",
    "release-replay",
}

INFRASTRUCTURE_DOCS = [
    "PRD.md",
    "RULES.md",
    "ARCHITECTURE.md",
    "DEVELOPMENT_LOG.md",
    "PLAN.md",
    "ADR.md",
]


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


class RepoHygieneTest(unittest.TestCase):
    def test_every_repo_skill_has_discoverable_frontmatter(self) -> None:
        skill_dir = ROOT / ".agents" / "skills"
        found = {p.parent.name for p in skill_dir.glob("*/SKILL.md")}
        self.assertEqual(found, SKILLS)
        for name in sorted(SKILLS):
            path = skill_dir / name / "SKILL.md"
            fields = _frontmatter(path)
            self.assertEqual(fields.get("name"), name)
            self.assertTrue(fields.get("description"), f"{name} is missing a description")
            self.assertGreater(len(path.read_text(encoding="utf-8")), 300, name)

    def test_skills_are_documented_for_agents(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for name in SKILLS:
            self.assertIn(name, agents)

    def test_governance_files_exist(self) -> None:
        for rel in [
            "LICENSE",
            "CHANGELOG.md",
            "docs/RISK.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/pull_request_template.md",
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_project_infrastructure_docs_exist(self) -> None:
        for rel in INFRASTRUCTURE_DOCS:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_project_infrastructure_docs_are_linked(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for rel in INFRASTRUCTURE_DOCS:
            self.assertIn(rel, readme, rel)
        self.assertNotIn("docs/ARCHITECTURE.md", readme, "README still links the removed stale path")

    def test_infrastructure_docs_cover_required_contracts(self) -> None:
        checks = {
            "PRD.md": ["预设优先", "字段级", "非目标"],
            "RULES.md": ["未核验", "实时链路", "文档更新"],
            "ARCHITECTURE.md": ["只读资产", "用户数据", "Tkinter"],
            "DEVELOPMENT_LOG.md": ["根因", "正确做法"],
            "PLAN.md": ["阶段一", "200", "--min-cases"],
            "ADR.md": ["待决", "闭集"],
        }
        for rel, needles in checks.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            for needle in needles:
                self.assertIn(needle, text, f"{rel} is missing {needle}")

    def test_agents_keeps_honor_code_and_process_links(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("协作原则（八荣八耻）", agents)
        self.assertGreaterEqual(len(re.findall(r"以.+?为荣，以.+?为耻", agents)), 11)
        for needle in ("真实链路", "n < 10", "未核验", "RULES.md"):
            self.assertIn(needle, agents)

    def test_adr_records_accepted_and_pending_decisions(self) -> None:
        adr = (ROOT / "ADR.md").read_text(encoding="utf-8")
        for number in range(1, 9):
            self.assertIn(f"ADR-{number:03d}", adr)
        self.assertGreaterEqual(adr.count("待决"), 3)
        self.assertIn("决策索引", adr)

    def test_development_log_records_root_causes(self) -> None:
        log = (ROOT / "DEVELOPMENT_LOG.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(log.count("根因"), 5)
        self.assertGreaterEqual(log.count("正确做法"), 5)
        self.assertIn("模板分档", log)
        self.assertIn("未核验", log)

    def test_readme_links_risk_and_license(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/RISK.md", readme)
        self.assertIn("LICENSE", readme)
        self.assertRegex(readme, re.compile(r"反作弊|风险"))

    def test_bug_form_asks_for_resolution_and_screenshot(self) -> None:
        form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
        self.assertIn("分辨率", form)
        self.assertIn("截图", form)
        self.assertIn("required: true", form)


if __name__ == "__main__":
    unittest.main()
