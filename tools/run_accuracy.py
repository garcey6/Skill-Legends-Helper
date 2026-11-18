"""Offline recognition accuracy regression for the validation fixtures."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.live_recognize import load_assets, run_image  # noqa: E402

DEFAULT_META = ROOT / "samples" / "validation" / "meta.json"


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile; 0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    rank = max(1, min(len(ordered), math.ceil(float(p) / 100.0 * len(ordered))))
    return round(ordered[rank - 1], 2)


def _trim_trailing_none(values: Sequence[Optional[str]]) -> List[Optional[str]]:
    result = list(values)
    while result and result[-1] is None:
        result.pop()
    return result


def compute_metrics(cases: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compute slot/name accuracy, exact-case rate, and latency percentiles.

    ``slots_total`` uses the longer of expected/actual so an extra false
    positive is penalized. ``names_total`` counts non-null expected names.
    """
    slots_total = 0
    slots_correct = 0
    names_total = 0
    names_correct = 0
    exact_cases = 0
    latencies: List[float] = []
    failures: List[Dict[str, Any]] = []

    for index, case in enumerate(cases):
        expected = list(case.get("expected") or [])
        actual = list(case.get("actual") or [])
        width = max(len(expected), len(actual))
        slots_total += width
        for slot in range(width):
            if slot < len(expected) and slot < len(actual) and expected[slot] == actual[slot]:
                slots_correct += 1

        expected_names = [name for name in expected if name is not None]
        names_total += len(expected_names)
        for slot, name in enumerate(expected):
            if name is not None and slot < len(actual) and actual[slot] == name:
                names_correct += 1

        if expected == _trim_trailing_none(actual):
            exact_cases += 1
        else:
            failures.append(
                {
                    "name": case.get("name", f"case{index + 1}"),
                    "expected": expected,
                    "actual": actual,
                    "error": case.get("error"),
                }
            )

        latency = case.get("latency_ms")
        if latency is not None:
            latencies.append(float(latency))

    count = len(cases)
    return {
        "cases": count,
        "slots_total": slots_total,
        "slots_correct": slots_correct,
        "slot_accuracy": slots_correct / slots_total if slots_total else 0.0,
        "names_total": names_total,
        "names_correct": names_correct,
        "name_accuracy": names_correct / names_total if names_total else 0.0,
        "exact_cases": exact_cases,
        "exact_case_rate": exact_cases / count if count else 0.0,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "failures": failures,
    }


def strict_failure(metrics: Mapping[str, Any], min_cases: int = 0) -> bool:
    """Return True when a strict run should fail the build."""
    count = int(metrics.get("cases") or 0)
    if count == 0:
        return True
    if count < max(0, int(min_cases)):
        return True
    return bool(metrics.get("failures"))


def evaluate_validation(
    meta_path: Path = DEFAULT_META,
    base: Optional[Path] = None,
    assets: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta_path = Path(meta_path)
    base = Path(base) if base is not None else meta_path.parent
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assets = load_assets() if assets is None else assets

    cases: List[Dict[str, Any]] = []
    for case in meta.get("cases", []):
        expected = list(case.get("expected", {}).get("heroes") or [])
        path = base / case["client"]
        started = time.perf_counter()
        error: Optional[str] = None
        actual: List[Optional[str]] = []
        try:
            result = run_image(str(path), assets)
            actual = [c.get("name") for c in result.get("heroes", {}).get("candidates", [])]
        except Exception as exc:  # keep one bad frame from hiding the rest
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        cases.append(
            {
                "name": case.get("name", path.stem),
                "image": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "expected": expected,
                "actual": actual,
                "latency_ms": latency_ms,
                "error": error,
            }
        )

    return {
        "meta": str(meta_path),
        "metrics": compute_metrics(cases),
        "cases": cases,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", type=Path, default=DEFAULT_META, help="validation meta.json")
    parser.add_argument("--base", type=Path, default=None, help="directory containing case images")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--strict", action="store_true", help="exit 1 on any mismatch or empty set")
    parser.add_argument(
        "--min-cases",
        type=int,
        default=0,
        help="with --strict, require at least this many cases",
    )
    args = parser.parse_args(argv)

    report = evaluate_validation(args.meta, args.base)
    report["strict"] = {
        "min_cases": max(0, args.min_cases),
        "failed": strict_failure(report["metrics"], args.min_cases),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")

    return 1 if args.strict and report["strict"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
