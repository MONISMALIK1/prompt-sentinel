"""
Assertion scorers — check whether LLM output satisfies expectations.

Supported assertion types:
  contains       — output must include this string (case-insensitive)
  not_contains   — output must NOT include this string
  exact          — output must exactly match (stripped)
  regex          — output must match this regex pattern
  json_valid     — output must be parseable JSON
  json_schema    — output JSON must match this schema (subset check)
  min_length     — output must be at least N characters
  max_length     — output must be at most N characters
  starts_with    — output must start with this string
  ends_with      — output must end with this string
"""

import re
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    assertion_type: str
    expected: Any
    passed: bool
    reason: str


def score(actual_output: str, assertions: list[dict]) -> tuple[float, list[AssertionResult]]:
    """
    Run all assertions against actual_output.
    Returns (score_0_to_1, list_of_results).
    Score = fraction of assertions that passed.
    """
    if not assertions:
        # No assertions → treat as pass with similarity to golden
        return 1.0, []

    results = []
    for assertion in assertions:
        result = _run_assertion(actual_output, assertion)
        results.append(result)

    passed = sum(1 for r in results if r.passed)
    score = passed / len(results) if results else 1.0
    return score, results


def _run_assertion(output: str, assertion: dict) -> AssertionResult:
    if "contains" in assertion:
        val = assertion["contains"]
        passed = val.lower() in output.lower()
        return AssertionResult(
            "contains", val, passed,
            "" if passed else f"Output does not contain '{val}'"
        )

    if "not_contains" in assertion:
        val = assertion["not_contains"]
        passed = val.lower() not in output.lower()
        return AssertionResult(
            "not_contains", val, passed,
            "" if passed else f"Output unexpectedly contains '{val}'"
        )

    if "exact" in assertion:
        val = assertion["exact"]
        passed = output.strip() == val.strip()
        return AssertionResult(
            "exact", val, passed,
            "" if passed else f"Expected exact match. Got: {output[:80]!r}"
        )

    if "regex" in assertion:
        pattern = assertion["regex"]
        flags = re.IGNORECASE if assertion.get("ignore_case", True) else 0
        passed = bool(re.search(pattern, output, flags))
        return AssertionResult(
            "regex", pattern, passed,
            "" if passed else f"Regex '{pattern}' did not match output"
        )

    if "json_valid" in assertion:
        try:
            json.loads(output)
            passed = True
            reason = ""
        except json.JSONDecodeError as e:
            passed = False
            reason = f"Output is not valid JSON: {e}"
        return AssertionResult("json_valid", True, passed, reason)

    if "json_schema" in assertion:
        schema = assertion["json_schema"]
        try:
            data = json.loads(output)
            missing = [k for k in schema if k not in data]
            passed = len(missing) == 0
            reason = "" if passed else f"Missing keys in JSON output: {missing}"
        except json.JSONDecodeError as e:
            passed = False
            reason = f"Output is not valid JSON: {e}"
        return AssertionResult("json_schema", schema, passed, reason)

    if "min_length" in assertion:
        val = int(assertion["min_length"])
        passed = len(output) >= val
        return AssertionResult(
            "min_length", val, passed,
            "" if passed else f"Output length {len(output)} < minimum {val}"
        )

    if "max_length" in assertion:
        val = int(assertion["max_length"])
        passed = len(output) <= val
        return AssertionResult(
            "max_length", val, passed,
            "" if passed else f"Output length {len(output)} > maximum {val}"
        )

    if "starts_with" in assertion:
        val = assertion["starts_with"]
        passed = output.strip().startswith(val)
        return AssertionResult(
            "starts_with", val, passed,
            "" if passed else f"Output does not start with '{val}'"
        )

    if "ends_with" in assertion:
        val = assertion["ends_with"]
        passed = output.strip().endswith(val)
        return AssertionResult(
            "ends_with", val, passed,
            "" if passed else f"Output does not end with '{val}'"
        )

    # Unknown assertion type — skip it
    return AssertionResult(
        "unknown", assertion, True,
        f"Unknown assertion type — skipped: {list(assertion.keys())}"
    )


def similarity_score(golden: str, actual: str) -> float:
    """
    Simple token-overlap similarity (0.0 – 1.0).
    Used when no assertions are defined — measures drift from golden output.
    """
    if not golden and not actual:
        return 1.0
    if not golden or not actual:
        return 0.0

    golden_tokens = set(golden.lower().split())
    actual_tokens = set(actual.lower().split())

    intersection = golden_tokens & actual_tokens
    union = golden_tokens | actual_tokens

    return len(intersection) / len(union) if union else 1.0
