from __future__ import annotations

import unittest

from tools.run_accuracy import compute_metrics, percentile


class AccuracyMetricsTest(unittest.TestCase):
    def test_compute_metrics_counts_slots_names_and_exact_cases(self) -> None:
        cases = [
            {"expected": ["A", "B", "C"], "actual": ["A", "B", "C"], "latency_ms": 100.0},
            {"expected": ["A", "B"], "actual": ["A", "B", "C"], "latency_ms": 300.0},
            {"expected": ["A", "B", "C"], "actual": ["A", None, "C"], "latency_ms": 200.0},
        ]

        metrics = compute_metrics(cases)

        self.assertEqual(metrics["cases"], 3)
        self.assertEqual(metrics["slots_total"], 9)
        self.assertEqual(metrics["slots_correct"], 7)
        self.assertAlmostEqual(metrics["slot_accuracy"], 7 / 9)
        self.assertEqual(metrics["names_total"], 8)
        self.assertEqual(metrics["names_correct"], 7)
        self.assertAlmostEqual(metrics["name_accuracy"], 7 / 8)
        self.assertEqual(metrics["exact_cases"], 1)
        self.assertAlmostEqual(metrics["exact_case_rate"], 1 / 3)
        self.assertEqual(metrics["p50_ms"], 200.0)
        self.assertEqual(metrics["p95_ms"], 300.0)
        self.assertEqual(len(metrics["failures"]), 2)

    def test_percentile_uses_nearest_rank(self) -> None:
        self.assertEqual(percentile([], 50), 0.0)
        self.assertEqual(percentile([10.0, 20.0, 30.0], 50), 20.0)
        self.assertEqual(percentile([10.0, 20.0, 30.0], 95), 30.0)
        self.assertEqual(percentile([5.0], 95), 5.0)

    def test_empty_cases_are_zero_not_a_crash(self) -> None:
        metrics = compute_metrics([])
        self.assertEqual(metrics["cases"], 0)
        self.assertEqual(metrics["slot_accuracy"], 0.0)
        self.assertEqual(metrics["name_accuracy"], 0.0)
        self.assertEqual(metrics["p95_ms"], 0.0)


class CurrentValidationCasesTest(unittest.TestCase):
    def test_current_validation_cases_match(self) -> None:
        from tools.run_accuracy import evaluate_validation

        report = evaluate_validation()
        self.assertGreaterEqual(report["metrics"]["cases"], 2)
        self.assertEqual(report["metrics"]["failures"], [])
        self.assertEqual(report["metrics"]["exact_case_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
