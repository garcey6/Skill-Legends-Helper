"""Hygiene checks for the real-frame holdout set."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT = ROOT / "samples" / "validation" / "holdout"
META = HOLDOUT / "meta.json"
FIXTURES = ROOT / "tests" / "fixtures"


def case_expected(case: dict) -> dict:
    if case.get("expected") is not None:
        return case["expected"]
    relative = case.get("expected_file")
    if not relative:
        return {}
    return json.loads((HOLDOUT / relative).read_text(encoding="utf-8"))


class HoldoutDatasetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(META.read_text(encoding="utf-8"))
        self.cases = self.data.get("cases") or []

    def test_has_at_least_nine_independent_cases(self) -> None:
        self.assertGreaterEqual(len(self.cases), 9)

    def test_every_case_has_a_real_image_and_labels(self) -> None:
        for case in self.cases:
            with self.subTest(case=case.get("name")):
                expected = case_expected(case)
                heroes = expected.get("heroes") or []
                self.assertGreaterEqual(len(heroes), 1)
                self.assertTrue(all(heroes), "empty hero name in %s" % case.get("name"))
                image_path = (HOLDOUT / str(case.get("client") or "")).resolve()
                self.assertTrue(image_path.is_file(), image_path)
                with Image.open(image_path) as image:
                    image.load()
                    self.assertEqual(list(image.size), list(case.get("resolution") or []))
                self.assertEqual(len(str(case.get("sha256") or "")), 64)

    def test_all_cases_use_fixture_expected_files(self) -> None:
        for case in self.cases:
            with self.subTest(case=case.get("name")):
                self.assertIsNone(case.get("expected"))
                expected_file = case.get("expected_file")
                self.assertTrue(expected_file)
                self.assertTrue((HOLDOUT / expected_file).is_file())
                self.assertTrue((HOLDOUT / str(case.get("client"))).is_file())

    def test_cases_are_not_the_same_frame_or_the_same_label_set(self) -> None:
        digests = [str(case.get("sha256") or "") for case in self.cases]
        self.assertEqual(len(digests), len(set(digests)), "duplicate image hash in holdout")

        labels = []
        for case in self.cases:
            expected = case_expected(case)
            schools = expected.get("schools")
            if isinstance(schools, dict):
                school_key = (
                    tuple(schools.get("enabled") or []),
                    tuple(schools.get("banned") or []),
                )
            else:
                school_key = tuple(schools or [])
            labels.append(
                (
                    tuple(case.get("resolution") or []),
                    tuple(expected.get("heroes") or []),
                    school_key,
                )
            )
        self.assertEqual(len(labels), len(set(labels)), "duplicate resolution+labels in holdout")


if __name__ == "__main__":
    unittest.main()
