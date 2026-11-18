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
