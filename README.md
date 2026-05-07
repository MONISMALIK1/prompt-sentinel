# prompt-sentinel 🛡️

**Git-native LLM prompt regression testing. No SaaS. No sign-up. One CLI.**

A company lost $2M because a 3-word prompt change silently broke their billing classifier in production. Nobody noticed for 6 days.

`prompt-sentinel` fixes this — record golden outputs, assert on every run, catch regressions in CI before they ship.

```bash
# 1. Record golden output
prompt-sentinel record \
  --name billing_classifier \
  --prompt prompts/billing.txt \
  --input "I need a refund"

# 2. Tweak your prompt, then test
prompt-sentinel test \
  --name billing_classifier \
  --prompt prompts/billing.txt \
  --input "I need a refund" \
  --assert '[{"contains": "refund"}, {"not_contains": "error"}]'

# Output:
# ✗ REGRESSION — Output similarity: 43%  (prompt sha: a1b2c3 → d4e5f6)
# - Output does not contain 'refund'
```

---

## Install

```bash
pip install prompt-sentinel
# For CI mode with sentinel.yaml:
pip install "prompt-sentinel[yaml]"
```

---

## Commands

### `record` — Capture golden baseline

Run your prompt against the LLM and save the output as the golden truth.

```bash
prompt-sentinel record \
  --name billing_classifier \
  --prompt prompts/billing.txt \
  --input "Please refund order #12345" \
  --model gpt-4o-mini
```

### `test` — Check for regressions

Run the prompt again and compare against golden. Exits `1` on regression.

```bash
prompt-sentinel test \
  --name billing_classifier \
  --prompt prompts/billing.txt \
  --input "Please refund order #12345" \
  --assert '[{"contains": "refund"}, {"min_length": 20}]'
```

### `diff` — Show what changed

```bash
prompt-sentinel diff \
  --name billing_classifier \
  --prompt prompts/billing.txt \
  --input "Please refund order #12345"
```

Shows a colored unified diff of prompt changes + output changes side by side.

### `list` — See all recorded suites

```bash
prompt-sentinel list
# Suite Name                     Cases   Last Run
# ─────────────────────────────────────────────────
#   billing_classifier               3   2026-05-07 11:20:44
#   support_router                   2   2026-05-07 11:21:01
```

### `ci` — Run full suite from YAML config

```bash
prompt-sentinel ci --config sentinel.yaml
# exits 0 = all passed
# exits 1 = regression detected
```

---

## sentinel.yaml

Define your entire test suite in one file:

```yaml
model: gpt-4o-mini
temperature: 0.0
regression_threshold: 0.80   # 80% output similarity required

suites:
  - name: billing_classifier
    prompt: prompts/billing_classifier.txt
    cases:
      - input: "I need a refund for my last order"
        assert:
          - contains: "refund"
          - not_contains: "error"
          - min_length: 10

      - input: "Cancel my subscription immediately"
        assert:
          - contains: "cancel"

  - name: support_router
    prompt: prompts/support_router.txt
    cases:
      - input: "My account is locked"
        assert:
          - contains: "account"
          - max_length: 500
```

---

## Assertion Types

| Assertion | Example | Description |
|---|---|---|
| `contains` | `{"contains": "refund"}` | Output must include string (case-insensitive) |
| `not_contains` | `{"not_contains": "error"}` | Output must NOT include string |
| `exact` | `{"exact": "Category: refund"}` | Exact string match (stripped) |
| `regex` | `{"regex": "Order #\\d+"}` | Regex pattern match |
| `json_valid` | `{"json_valid": true}` | Output must be valid JSON |
| `json_schema` | `{"json_schema": {"status": null}}` | JSON output must have these keys |
| `min_length` | `{"min_length": 20}` | Output must be ≥ N characters |
| `max_length` | `{"max_length": 500}` | Output must be ≤ N characters |
| `starts_with` | `{"starts_with": "Category:"}` | Output starts with string |
| `ends_with` | `{"ends_with": "."}` | Output ends with string |

No assertions? Sentinel falls back to **token-overlap similarity** vs the golden output. Regression fires below `regression_threshold` (default: 80%).

---

## GitHub Actions

Drop this in `.github/workflows/sentinel.yml` — regressions appear as red ✗ annotations directly in your PR:

```yaml
name: Prompt Regression Tests
on:
  push:
    paths: ['prompts/**', 'sentinel.yaml']

jobs:
  regression-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install "prompt-sentinel[yaml]"
      - run: prompt-sentinel ci --config sentinel.yaml
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

## How It Works

```
prompt-sentinel/
├── store.py        # SQLite snapshot store (.prompt-sentinel/db.sqlite)
├── runner.py       # LLM caller — OpenAI, Anthropic, any compatible API
├── scorer.py       # Assertion engine — 10 assertion types
├── differ.py       # Unified diff: prompt changes + output changes
├── reporter.py     # CI report + GitHub Actions annotations
├── config.py       # sentinel.yaml loader
└── cli.py          # Click CLI — record / test / diff / list / ci
```

**Design decisions:**
- **Zero infra** — everything in `.prompt-sentinel/db.sqlite` (add to `.gitignore` or commit it)
- **Stdlib-first** — only `click` required; `pyyaml` optional for CI mode
- **Prompt SHA tracking** — automatically detects when your prompt file changed between record and test
- **Similarity fallback** — even without assertions, drift from golden is caught
- **Exit codes** — `0` pass, `1` regression — plays nicely with any CI system

---

## Supported Models

Works with any model name. Auto-detects provider:
- **OpenAI**: `gpt-4o`, `gpt-4o-mini`, `o1`, `o3-mini`, `gpt-4-turbo`
- **Anthropic**: `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`
- **Custom**: pass `--base-url` for any OpenAI-compatible endpoint (Ollama, Together, Groq, etc.)

---

## Running Tests

```bash
pip install pytest click
pytest tests/ -v   # 34 tests, no API calls needed
```

---

## Future Improvements

- [ ] `--watch` mode: re-run tests on prompt file save
- [ ] Semantic similarity scorer (embeddings-based, optional dep)
- [ ] HTML report with side-by-side diff view
- [ ] Pytest plugin: `import pytest_sentinel`
- [ ] VS Code extension: inline regression warnings
- [ ] Golden import/export for team sharing

---

## Related

Built the same week as [agent-watchdog](https://github.com/MONISMALIK1/agent-watchdog) — loop detection + cost kill switch for LLM agents.

Together they cover the two biggest unguarded failure modes in production LLM apps:
- **agent-watchdog** → runtime safety (runaway loops, budget blowout)
- **prompt-sentinel** → deploy safety (prompt regressions, silent quality drift)

---

## License

MIT — Monis Malik
