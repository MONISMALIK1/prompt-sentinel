"""
CI report generator.
Outputs: terminal summary, JSON report, GitHub Actions annotations.
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional
from .differ import PromptDiff


@dataclass
class SuiteResult:
    name: str
    total_cases: int
    passed: int
    failed: int
    regressions: list[str]   # input texts that regressed
    diffs: list[PromptDiff]


@dataclass
class Report:
    total_suites: int
    total_cases: int
    passed: int
    failed: int
    suite_results: list[SuiteResult]
    has_regression: bool


def build_report(suite_results: list[SuiteResult]) -> Report:
    total_cases = sum(s.total_cases for s in suite_results)
    passed = sum(s.passed for s in suite_results)
    failed = sum(s.failed for s in suite_results)
    has_regression = any(s.failed > 0 for s in suite_results)

    return Report(
        total_suites=len(suite_results),
        total_cases=total_cases,
        passed=passed,
        failed=failed,
        suite_results=suite_results,
        has_regression=has_regression,
    )


def print_report(report: Report, color: bool = True):
    R = "\033[31m" if color else ""
    G = "\033[32m" if color else ""
    Y = "\033[33m" if color else ""
    BOLD = "\033[1m" if color else ""
    RESET = "\033[0m" if color else ""

    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}prompt-sentinel — CI Report{RESET}")
    print(f"{'═'*60}")

    for suite in report.suite_results:
        icon = f"{G}✓{RESET}" if suite.failed == 0 else f"{R}✗{RESET}"
        print(f"\n  {icon}  {BOLD}{suite.name}{RESET}")
        print(f"     Cases: {suite.total_cases}  |  Passed: {G}{suite.passed}{RESET}  |  Failed: {R}{suite.failed}{RESET}")
        if suite.regressions:
            for reg in suite.regressions:
                print(f"     {R}↳ REGRESSION:{RESET} {reg[:80]!r}")

    print(f"\n{'─'*60}")
    status = f"{G}ALL PASSED{RESET}" if not report.has_regression else f"{R}REGRESSIONS DETECTED{RESET}"
    print(f"Result: {BOLD}{status}{RESET}")
    print(f"Suites: {report.total_suites}  |  Cases: {report.total_cases}  |  Passed: {report.passed}  |  Failed: {report.failed}")
    print(f"{'═'*60}\n")


def write_json_report(report: Report, path: str = "sentinel-report.json"):
    """Write machine-readable JSON report."""
    data = {
        "total_suites": report.total_suites,
        "total_cases": report.total_cases,
        "passed": report.passed,
        "failed": report.failed,
        "has_regression": report.has_regression,
        "suites": [
            {
                "name": s.name,
                "total_cases": s.total_cases,
                "passed": s.passed,
                "failed": s.failed,
                "regressions": s.regressions,
            }
            for s in report.suite_results
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"JSON report written to {path}")


def emit_github_annotations(report: Report):
    """
    Emit GitHub Actions workflow commands for inline annotations.
    These appear as red ✗ marks in the PR diff view.
    """
    if not os.environ.get("GITHUB_ACTIONS"):
        return

    for suite in report.suite_results:
        for reg in suite.regressions:
            print(f"::error title=Prompt Regression [{suite.name}]::{reg[:200]}")

    if not report.has_regression:
        print(f"::notice title=prompt-sentinel::All {report.total_cases} cases passed ✓")
