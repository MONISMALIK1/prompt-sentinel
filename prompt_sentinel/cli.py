"""
prompt-sentinel CLI

Commands:
  record   — run a prompt + capture golden output
  test     — run and compare against golden
  diff     — show diff between last run and golden
  list     — list all recorded suites
  ci       — run full test suite from sentinel.yaml (exits 1 on regression)
"""

import sys
import os
import json
from pathlib import Path
from typing import Optional

try:
    import click
    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False

from .store import Store
from .runner import LLMRunner
from .scorer import score, similarity_score
from .differ import diff_run, format_diff
from .reporter import SuiteResult, build_report, print_report, write_json_report, emit_github_annotations


def _load_prompt(prompt_path: str) -> str:
    p = Path(prompt_path)
    if not p.exists():
        click.echo(f"Error: prompt file not found: {prompt_path}", err=True)
        sys.exit(1)
    return p.read_text().strip()


def _get_store(sentinel_dir: str) -> Store:
    return Store(root=sentinel_dir)


def _make_runner(model: str, api_key: Optional[str], base_url: Optional[str], temperature: float) -> LLMRunner:
    return LLMRunner(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


if HAS_CLICK:
    @click.group()
    @click.version_option("0.1.0", prog_name="prompt-sentinel")
    def cli():
        """prompt-sentinel — Git-native LLM prompt regression testing."""
        pass

    # ── record ────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--name", "-n", required=True, help="Suite name (e.g. billing_classifier)")
    @click.option("--prompt", "-p", required=True, help="Path to prompt file")
    @click.option("--input", "-i", "input_text", required=True, help="User input to test")
    @click.option("--model", "-m", default="gpt-4o-mini", show_default=True)
    @click.option("--api-key", envvar=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"], default=None)
    @click.option("--base-url", default=None, help="Custom OpenAI-compatible base URL")
    @click.option("--temperature", default=0.0, show_default=True)
    @click.option("--sentinel-dir", default=".", show_default=True, help="Directory for .prompt-sentinel/")
    def record(name, prompt, input_text, model, api_key, base_url, temperature, sentinel_dir):
        """Run a prompt and save its output as the golden baseline."""
        prompt_text = _load_prompt(prompt)
        store = _get_store(sentinel_dir)
        runner = _make_runner(model, api_key, base_url, temperature)

        click.echo(f"Running {model} for suite '{name}'...")
        try:
            resp = runner.run(system_prompt=prompt_text, user_input=input_text)
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        sha = store.save_golden(
            name=name,
            prompt_text=prompt_text,
            input_text=input_text,
            golden_output=resp.content,
            model=model,
        )

        click.echo(f"\n\033[32m✓ Golden recorded\033[0m")
        click.echo(f"  Suite  : {name}")
        click.echo(f"  SHA    : {sha[:8]}")
        click.echo(f"  Tokens : {resp.input_tokens} in / {resp.output_tokens} out")
        click.echo(f"  Output preview: {resp.content[:120]!r}")

    # ── test ──────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--name", "-n", required=True, help="Suite name")
    @click.option("--prompt", "-p", required=True, help="Path to prompt file")
    @click.option("--input", "-i", "input_text", required=True, help="User input to test")
    @click.option("--assert", "-a", "assertions_json", default=None,
                  help='JSON assertions e.g. \'[{"contains":"refund"}]\'')
    @click.option("--model", "-m", default=None, help="Override model from golden")
    @click.option("--api-key", envvar=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"], default=None)
    @click.option("--base-url", default=None)
    @click.option("--temperature", default=0.0, show_default=True)
    @click.option("--regression-threshold", default=0.80, show_default=True)
    @click.option("--sentinel-dir", default=".", show_default=True)
    @click.option("--fail-on-regression/--no-fail", default=True, show_default=True)
    def test(name, prompt, input_text, assertions_json, model, api_key, base_url,
             temperature, regression_threshold, sentinel_dir, fail_on_regression):
        """Run a prompt and compare output to the recorded golden baseline."""
        prompt_text = _load_prompt(prompt)
        store = _get_store(sentinel_dir)

        golden = store.get_golden(name, input_text)
        if not golden:
            click.echo(f"No golden found for suite '{name}' + input. Run 'record' first.", err=True)
            sys.exit(1)

        use_model = model or golden.model
        runner = _make_runner(use_model, api_key, base_url, temperature)

        click.echo(f"Testing suite '{name}' with {use_model}...")
        try:
            resp = runner.run(system_prompt=prompt_text, user_input=input_text)
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Score
        assertions = json.loads(assertions_json) if assertions_json else []
        if assertions:
            final_score, assertion_results = score(resp.content, assertions)
            failure_reasons = [r.reason for r in assertion_results if not r.passed and r.reason]
            passed = final_score >= regression_threshold
        else:
            final_score = similarity_score(golden.golden_output, resp.content)
            failure_reasons = []
            passed = final_score >= regression_threshold

        store.save_run(
            name=name,
            prompt_text=prompt_text,
            input_text=input_text,
            actual_output=resp.content,
            model=use_model,
            passed=passed,
            score=final_score,
            failure_reasons=failure_reasons,
        )

        # Show diff
        run = store.get_last_run(name, input_text)
        d = diff_run(golden, run, prompt_text, regression_threshold)
        click.echo(format_diff(d))

        if failure_reasons:
            click.echo("\n\033[31mFailed assertions:\033[0m")
            for reason in failure_reasons:
                click.echo(f"  • {reason}")

        if not passed and fail_on_regression:
            sys.exit(1)

    # ── diff ──────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--name", "-n", required=True)
    @click.option("--input", "-i", "input_text", required=True)
    @click.option("--prompt", "-p", required=True)
    @click.option("--sentinel-dir", default=".")
    def diff(name, input_text, prompt, sentinel_dir):
        """Show diff between last run and the golden baseline."""
        prompt_text = _load_prompt(prompt)
        store = _get_store(sentinel_dir)

        golden = store.get_golden(name, input_text)
        run = store.get_last_run(name, input_text)

        if not golden:
            click.echo("No golden found. Run 'record' first.", err=True)
            sys.exit(1)
        if not run:
            click.echo("No run found. Run 'test' first.", err=True)
            sys.exit(1)

        d = diff_run(golden, run, prompt_text)
        click.echo(format_diff(d))

    # ── list ──────────────────────────────────────────────────────────────────
    @cli.command("list")
    @click.option("--sentinel-dir", default=".")
    def list_suites(sentinel_dir):
        """List all recorded suites."""
        store = _get_store(sentinel_dir)
        names = store.list_names()

        if not names:
            click.echo("No suites recorded yet. Use 'record' to get started.")
            return

        click.echo(f"\n{'Suite Name':<30} {'Cases':>6}  {'Last Run':>25}")
        click.echo("─" * 65)
        for name in names:
            goldens = store.get_goldens(name)
            runs = store.get_runs(name, limit=1)
            last_run = runs[0].ran_at[:19].replace("T", " ") if runs else "never"
            click.echo(f"  {name:<28} {len(goldens):>6}  {last_run:>25}")
        click.echo()

    # ── ci ────────────────────────────────────────────────────────────────────
    @cli.command()
    @click.option("--config", "-c", default="sentinel.yaml", show_default=True)
    @click.option("--api-key", envvar=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"], default=None)
    @click.option("--sentinel-dir", default=".", show_default=True)
    @click.option("--json-report", default=None, help="Write JSON report to this path")
    @click.option("--record-missing/--no-record-missing", default=False,
                  help="Auto-record goldens that don't exist yet")
    def ci(config, api_key, sentinel_dir, json_report, record_missing):
        """Run full test suite from sentinel.yaml. Exits 1 on any regression."""
        from .config import load_config

        try:
            cfg = load_config(config)
        except FileNotFoundError:
            click.echo(f"Config file not found: {config}", err=True)
            sys.exit(1)
        except ImportError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

        store = _get_store(sentinel_dir)
        suite_results = []

        for suite in cfg.suites:
            prompt_path = Path(config).parent / suite.prompt_file
            if not prompt_path.exists():
                click.echo(f"Prompt file not found: {prompt_path}", err=True)
                continue

            prompt_text = prompt_path.read_text().strip()
            model = suite.model or cfg.model
            runner = _make_runner(model, api_key, None, cfg.temperature)

            passed_count = 0
            failed_count = 0
            regressions = []
            diffs = []

            click.echo(f"\nRunning suite: {suite.name} ({len(suite.cases)} cases)")

            for case in suite.cases:
                golden = store.get_golden(suite.name, case.input)

                if not golden:
                    if record_missing:
                        click.echo(f"  Recording missing golden for: {case.input[:50]!r}")
                        try:
                            resp = runner.run(system_prompt=prompt_text, user_input=case.input)
                            store.save_golden(
                                name=suite.name, prompt_text=prompt_text,
                                input_text=case.input, golden_output=resp.content, model=model,
                            )
                            golden = store.get_golden(suite.name, case.input)
                        except RuntimeError as e:
                            click.echo(f"  Error: {e}", err=True)
                            continue
                    else:
                        click.echo(f"  \033[33m⚠ No golden for: {case.input[:50]!r} — skipping (use --record-missing)\033[0m")
                        continue

                try:
                    resp = runner.run(system_prompt=prompt_text, user_input=case.input)
                except RuntimeError as e:
                    click.echo(f"  Error: {e}", err=True)
                    failed_count += 1
                    regressions.append(str(e)[:100])
                    continue

                final_score, assertion_results = score(resp.content, case.assertions)
                failure_reasons = [r.reason for r in assertion_results if not r.passed and r.reason]

                if not case.assertions:
                    final_score = similarity_score(golden.golden_output, resp.content)
                    failure_reasons = []

                passed = final_score >= cfg.regression_threshold

                store.save_run(
                    name=suite.name, prompt_text=prompt_text,
                    input_text=case.input, actual_output=resp.content,
                    model=model, passed=passed, score=final_score,
                    failure_reasons=failure_reasons,
                )

                run = store.get_last_run(suite.name, case.input)
                d = diff_run(golden, run, prompt_text, cfg.regression_threshold)
                diffs.append(d)

                icon = "\033[32m✓\033[0m" if passed else "\033[31m✗\033[0m"
                click.echo(f"  {icon}  {case.input[:55]!r}  ({final_score:.0%})")

                if passed:
                    passed_count += 1
                else:
                    failed_count += 1
                    regressions.append(case.input)

            suite_results.append(SuiteResult(
                name=suite.name,
                total_cases=passed_count + failed_count,
                passed=passed_count,
                failed=failed_count,
                regressions=regressions,
                diffs=diffs,
            ))

        report = build_report(suite_results)
        print_report(report)
        emit_github_annotations(report)

        if json_report:
            write_json_report(report, json_report)

        sys.exit(1 if report.has_regression else 0)


def main():
    if not HAS_CLICK:
        print("Error: click is required. Install it: pip install click")
        sys.exit(1)
    cli()
