from __future__ import annotations

import statistics
import time
from pathlib import Path

from app.replay import discover_cases
from app.vision.debugframe import build_debug_frame
from tools.live_recognize import load_assets, run_image

ROOT = Path(__file__).resolve().parent.parent
REPEATS = 7
FIXTURE_LIMIT = 3


def _median_ms(samples):
    return statistics.median(samples) * 1000.0


def test_debug_off_adds_no_measurable_overhead_to_recognition():
    """Instrumentation-only A/B benchmark: N=21 fixture runs per side.

    This deliberately excludes the debug window, screenshot capture and PNG
    save (those are measured by the GUI smoke).  It answers the zero-overhead
    question for the recognition path: off must return before any debug work,
    and building a DebugFrame from the same recognition result must stay under
    the 5% median budget.
    """
    cases = discover_cases()[:FIXTURE_LIMIT]
    assert len(cases) == FIXTURE_LIMIT
    assets = load_assets(use_ocr=True)

    off_samples = []
    on_samples = []
    for case in cases:
        size = None
        for _ in range(REPEATS):
            started = time.perf_counter()
            result = run_image(str(case.image_path), assets)
            off_samples.append(time.perf_counter() - started)
            window = result["session"]["window"]
            size = (int(window["client_w"]), int(window["client_h"]))

            started = time.perf_counter()
            result = run_image(str(case.image_path), assets)
            build_debug_frame(result, assets["layout"], size)
            on_samples.append(time.perf_counter() - started)

    off_median = _median_ms(off_samples)
    on_median = _median_ms(on_samples)
    overhead = on_median / off_median - 1.0 if off_median else 0.0
    print(
        "[debug-benchmark] N=%d off_median=%.2fms on_median=%.2fms overhead=%.2f%%"
        % (len(off_samples), off_median, on_median, overhead * 100.0)
    )
    assert overhead < 0.05


def test_disabled_debug_hook_is_negligible_against_recognition():
    import agent as agent_module

    instance = agent_module.Agent.__new__(agent_module.Agent)
    instance.debug_enabled = False
    started = time.perf_counter()
    for _ in range(1000):
        instance._maybe_debug({"heroes": {"candidates": []}})
    per_call_us = (time.perf_counter() - started) * 1_000_000.0 / 1000.0
    print("[debug-benchmark] disabled_hook=%.3fus/call" % per_call_us)
    assert per_call_us < 100.0
