from __future__ import annotations

import unittest
from pathlib import Path

from app.replay import discover_cases, recognize_image, run_case

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "screenshots"


class CrossResolutionRecognitionTest(unittest.TestCase):
    def test_2560x80_strip_does_not_overcount_icon_runs(self):
        result = recognize_image(FIXTURES / "screenshot_2560_80.png")
        schools = result["schools"]

        self.assertEqual(schools["run_count"], 8)
        self.assertNotIn("图标条 run 数", "\n".join(result.get("warnings") or []))

    def test_annotated_fixture_replay_still_reads_expected_heroes(self):
        cases = {case.name: case for case in discover_cases()}
        case = cases["draft001_1800x1118"]

        self.assertIsNotNone(case.annotation)
        result = run_case(case)

        self.assertEqual(result["heroes"], ["森林游侠", "神秘法师", "魔镜"])


if __name__ == "__main__":
    unittest.main()
