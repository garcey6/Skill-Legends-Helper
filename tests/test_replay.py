"""M1 static replay tests: real fixtures, CLI and capture-source aliases."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from app.live.replaysrc import ImageFrameSource
from app.live.frame import FrameSource
from app.live.sources import CaptureSource, StaticFrameSource


# 此阈值随 fixtures 增长同步上调，禁止下调。
# M1 起点是两条已迁移的真实 holdout 用例；PLAN 阶段一目标是 10 条。
FIXTURE_MINIMUM = 2
FIXTURE_TARGET = 10


class FixtureDiscoveryTest(unittest.TestCase):
    def test_discovers_the_two_migrated_holdout_cases(self) -> None:
        from app.replay import discover_cases

        names = {case.name for case in discover_cases()}
        self.assertIn("draft001_1800x1118", names)
        self.assertIn("draft002_2153x1179", names)

    def test_fixture_count_meets_the_rising_floor(self) -> None:
        from app.replay import discover_cases

        cases = discover_cases()
        print(
            "holdout 用例数：%d / 目标 %d，缺口 %d"
            % (len(cases), FIXTURE_TARGET, max(0, FIXTURE_TARGET - len(cases)))
        )
        self.assertGreaterEqual(len(cases), FIXTURE_MINIMUM)

    def test_every_fixture_matches_heroes_schools_and_confidence(self) -> None:
        from app.replay import discover_cases, run_case

        failures = []
        for case in discover_cases():
            try:
                result = run_case(case)
            except Exception as exc:  # report the case, not just a stack
                failures.append("%s: %s: %s" % (case.name, type(exc).__name__, exc))
                continue
            expected = case.expected
            if result["heroes"] != list(expected.get("heroes") or []):
                failures.append(
                    "%s heroes %r != %r"
                    % (case.name, result["heroes"], expected.get("heroes"))
                )
            schools = expected.get("schools")
            if schools is not None:
                if isinstance(schools, dict):
                    expected_enabled = list(schools.get("enabled") or [])
                    expected_banned = schools.get("banned")
                else:
                    expected_enabled = list(schools)
                    expected_banned = None
                actual = result["schools"]
                if sorted(actual.get("enabled") or []) != sorted(expected_enabled):
                    failures.append(
                        "%s enabled %r != %r"
                        % (case.name, actual.get("enabled"), expected_enabled)
                    )
                if expected_banned is not None and sorted(actual.get("banned") or []) != sorted(
                    expected_banned
                ):
                    failures.append(
                        "%s banned %r != %r"
                        % (case.name, actual.get("banned"), expected_banned)
                    )
            floor = float(expected.get("min_confidence") or 0.0)
            if floor and min(result["scores"] or [0.0]) < floor:
                failures.append("%s confidence below %.3f" % (case.name, floor))
        self.assertEqual(failures, [])


class ReplayCliTest(unittest.TestCase):
    def test_replay_cli_prints_json_for_a_real_fixture(self) -> None:
        from app.replay import discover_cases, main

        case = discover_cases()[0]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--replay", str(case.image_path)])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["heroes"], case.expected["heroes"])

    def test_generate_expected_writes_a_draft_json(self) -> None:
        from app.replay import discover_cases, generate_expected

        case = discover_cases()[0]
        with tempfile.TemporaryDirectory() as tmp:
            target = generate_expected(case.image_path, Path(tmp))
            payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(target.name, case.image_path.stem + ".json")
        self.assertEqual(payload["heroes"], case.expected["heroes"])
        self.assertIn("schools", payload)


class CaptureSourceTest(unittest.TestCase):
    def test_capture_source_is_a_compatibility_alias(self) -> None:
        self.assertIs(CaptureSource, FrameSource)
        self.assertIs(StaticFrameSource, ImageFrameSource)

    def test_static_source_implements_the_frame_interface(self) -> None:
        from app.replay import discover_cases

        case = discover_cases()[0]
        source = StaticFrameSource(case.image_path)
        state = source.state()
        self.assertTrue(state.found)
        self.assertGreater(state.client_w, 0)
        self.assertIsNotNone(source.grab((0.0, 1.0, 0.0, 1.0)))


if __name__ == "__main__":
    unittest.main()
