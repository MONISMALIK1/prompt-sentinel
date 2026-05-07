"""
Diff engine — compares current prompt/output against golden baseline.
Produces human-readable and machine-readable diffs.
"""

import difflib
from dataclasses import dataclass
from typing import Optional
from .store import GoldenRecord, RunRecord
from .scorer import similarity_score


@dataclass
class PromptDiff:
    name: str
    input_text: str
    prompt_changed: bool
    prompt_sha_golden: str
    prompt_sha_current: str
    prompt_diff_lines: list[str]
    output_similarity: float
    golden_output: str
    actual_output: str
    output_diff_lines: list[str]
    is_regression: bool
    regression_threshold: float


def diff_run(
    golden: GoldenRecord,
    run: RunRecord,
    current_prompt: str,
    regression_threshold: float = 0.80,
) -> PromptDiff:
    from .store import _sha256

    current_sha = _sha256(current_prompt)
    prompt_changed = current_sha != golden.prompt_sha

    # Prompt diff
    prompt_diff = list(
        difflib.unified_diff(
            golden.prompt_text.splitlines(keepends=True),
            current_prompt.splitlines(keepends=True),
            fromfile="golden_prompt",
            tofile="current_prompt",
            lineterm="",
        )
    )

    # Output diff
    output_diff = list(
        difflib.unified_diff(
            golden.golden_output.splitlines(keepends=True),
            run.actual_output.splitlines(keepends=True),
            fromfile="golden_output",
            tofile="actual_output",
            lineterm="",
        )
    )

    sim = similarity_score(golden.golden_output, run.actual_output)
    is_regression = not run.passed or sim < regression_threshold

    return PromptDiff(
        name=golden.name,
        input_text=golden.input_text,
        prompt_changed=prompt_changed,
        prompt_sha_golden=golden.prompt_sha,
        prompt_sha_current=current_sha,
        prompt_diff_lines=prompt_diff,
        output_similarity=sim,
        golden_output=golden.golden_output,
        actual_output=run.actual_output,
        output_diff_lines=output_diff,
        is_regression=is_regression,
        regression_threshold=regression_threshold,
    )


def format_diff(diff: PromptDiff, color: bool = True) -> str:
    lines = []
    R = "\033[31m" if color else ""
    G = "\033[32m" if color else ""
    Y = "\033[33m" if color else ""
    B = "\033[36m" if color else ""
    BOLD = "\033[1m" if color else ""
    RESET = "\033[0m" if color else ""

    status = f"{R}✗ REGRESSION{RESET}" if diff.is_regression else f"{G}✓ PASS{RESET}"
    lines.append(f"\n{BOLD}{'─'*60}{RESET}")
    lines.append(f"{BOLD}Suite: {diff.name}{RESET}  |  Input: {diff.input_text[:60]!r}")
    lines.append(f"Status: {status}  |  Output similarity: {diff.output_similarity:.0%}")

    if diff.prompt_changed:
        lines.append(f"\n{Y}⚠ PROMPT CHANGED{RESET}  ({diff.prompt_sha_golden[:8]} → {diff.prompt_sha_current[:8]})")
        if diff.prompt_diff_lines:
            lines.append("")
            for line in diff.prompt_diff_lines[:30]:
                if line.startswith("+"):
                    lines.append(f"  {G}{line}{RESET}")
                elif line.startswith("-"):
                    lines.append(f"  {R}{line}{RESET}")
                else:
                    lines.append(f"  {line}")
    else:
        lines.append(f"Prompt: unchanged  (sha: {diff.prompt_sha_golden[:8]})")

    if diff.output_diff_lines:
        lines.append(f"\n{B}Output diff:{RESET}")
        for line in diff.output_diff_lines[:40]:
            if line.startswith("+"):
                lines.append(f"  {G}{line}{RESET}")
            elif line.startswith("-"):
                lines.append(f"  {R}{line}{RESET}")
            else:
                lines.append(f"  {line}")

    return "\n".join(lines)
