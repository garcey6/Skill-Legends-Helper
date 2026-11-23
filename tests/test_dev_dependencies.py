"""M1 dependency and release-hygiene guards."""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DevDependencyTest(unittest.TestCase):
    def test_requirements_dev_inherits_runtime_and_pins_pytest(self) -> None:
        path = ROOT / "requirements-dev.txt"
        self.assertTrue(path.is_file(), "requirements-dev.txt is required for M1")
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertIn("-r requirements.txt", lines)
        pytest_lines = [line for line in lines if line.startswith("pytest")]
        self.assertEqual(len(pytest_lines), 1, pytest_lines)
        self.assertRegex(pytest_lines[0], r"^pytest==\d+\.\d+\.\d+$")
        self.assertNotIn(">=", pytest_lines[0])

    def test_ci_installs_runtime_then_dev_dependencies(self) -> None:
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements.txt", text)
        self.assertIn("pip install -r requirements-dev.txt", text)
        self.assertLess(
            text.index("pip install -r requirements.txt"),
            text.index("pip install -r requirements-dev.txt"),
        )
        self.assertIn("pytest", text)

    def test_release_excludes_pytest_and_tests(self) -> None:
        from tools.build_release import _pyinstaller_command

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = _pyinstaller_command(
                root=root,
                entry=root / "agent.py",
                stage=root / "stage",
                dist=root / "dist",
                work=root / "work",
                spec=root / "spec",
                name="XuanJiHelper",
            )
        pairs = list(zip(command, command[1:]))
        for module in ("pytest", "_pytest", "tests", "test"):
            self.assertIn(("--exclude-module", module), pairs)


if __name__ == "__main__":
    unittest.main()
