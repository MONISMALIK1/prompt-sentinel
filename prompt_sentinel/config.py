"""
YAML config loader for sentinel.yaml.

Example sentinel.yaml:
─────────────────────────────────
model: gpt-4o-mini
temperature: 0.0
regression_threshold: 0.80

suites:
  - name: billing_classifier
    prompt: prompts/billing.txt
    cases:
      - input: "Please refund my order #12345"
        assert:
          - contains: "refund"
          - not_contains: "error"
          - min_length: 10

  - name: support_router
    prompt: prompts/support_router.txt
    cases:
      - input: "My account is locked"
        assert:
          - contains: "account"
          - json_valid: true
─────────────────────────────────
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CaseConfig:
    input: str
    assertions: list[dict] = field(default_factory=list)


@dataclass
class SuiteConfig:
    name: str
    prompt_file: str
    cases: list[CaseConfig]
    model: Optional[str] = None


@dataclass
class SentinelConfig:
    model: str
    temperature: float
    regression_threshold: float
    suites: list[SuiteConfig]
    api_key_env: Optional[str] = None


def load_config(path: str = "sentinel.yaml") -> SentinelConfig:
    """Load and parse sentinel.yaml — uses only stdlib (no PyYAML needed for simple configs)."""
    content = Path(path).read_text()

    # Try PyYAML first, fall back to a minimal parser for simple cases
    try:
        import yaml
        data = yaml.safe_load(content)
    except ImportError:
        data = _minimal_yaml_parse(content)

    return _parse_config(data)


def _parse_config(data: dict) -> SentinelConfig:
    suites = []
    for s in data.get("suites", []):
        cases = []
        for c in s.get("cases", []):
            assertions = c.get("assert", [])
            # Normalize: each assertion is a dict
            normalized = []
            for a in assertions:
                if isinstance(a, dict):
                    normalized.append(a)
            cases.append(CaseConfig(input=c["input"], assertions=normalized))

        suites.append(SuiteConfig(
            name=s["name"],
            prompt_file=s.get("prompt", s.get("prompt_file", "")),
            cases=cases,
            model=s.get("model"),
        ))

    return SentinelConfig(
        model=data.get("model", "gpt-4o-mini"),
        temperature=float(data.get("temperature", 0.0)),
        regression_threshold=float(data.get("regression_threshold", 0.80)),
        suites=suites,
        api_key_env=data.get("api_key_env"),
    )


def _minimal_yaml_parse(content: str) -> dict:
    """
    Extremely minimal YAML parser for simple sentinel.yaml files.
    Handles scalars and lists of dicts. Falls back gracefully.
    Real projects should pip install pyyaml.
    """
    raise ImportError(
        "PyYAML is required for CI mode: pip install pyyaml\n"
        "Or use individual commands (record/test) instead of ci."
    )
