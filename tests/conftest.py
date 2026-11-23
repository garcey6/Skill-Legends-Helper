"""Pytest presentation hooks for the M1 fixture suite.

The fixture count is printed in every pytest run so the gap to the PLAN phase
one target cannot disappear behind a green suite.
"""
from __future__ import annotations


def pytest_report_header(config) -> str:
    try:
        from app.replay import FIXTURE_TARGET, discover_cases

        count = len(discover_cases())
        return "holdout 用例数：%d / 目标 %d，缺口 %d" % (
            count,
            FIXTURE_TARGET,
            max(0, FIXTURE_TARGET - count),
        )
    except Exception as exc:  # keep collection errors visible in the test body
        return "holdout 用例数：unavailable (%s)" % exc


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Print the gap even when pytest runs with ``-q``."""
    terminalreporter.write_line(pytest_report_header(config))

