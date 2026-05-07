import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from prompt_sentinel.store import Store, _sha256
from prompt_sentinel.differ import diff_run, format_diff


@pytest.fixture
def populated_store(tmp_path):
    store = Store(root=str(tmp_path))
    store.save_golden("billing", "You classify billing requests.", "Refund my order", "Category: refund", "gpt-4o-mini")
    store.save_run("billing", "You classify billing requests.", "Refund my order",
                   "Category: refund", "gpt-4o-mini", passed=True, score=1.0, failure_reasons=[])
    return store


def test_no_regression_identical_output(populated_store):
    golden = populated_store.get_golden("billing", "Refund my order")
    run = populated_store.get_last_run("billing", "Refund my order")
    d = diff_run(golden, run, "You classify billing requests.", regression_threshold=0.80)
    assert not d.is_regression
    assert not d.prompt_changed
    assert d.output_similarity == 1.0


def test_prompt_changed_detection(populated_store):
    golden = populated_store.get_golden("billing", "Refund my order")
    run = populated_store.get_last_run("billing", "Refund my order")
    d = diff_run(golden, run, "You are a NEW billing classifier.", regression_threshold=0.80)
    assert d.prompt_changed


def test_regression_detected_on_low_similarity(populated_store):
    store = populated_store
    store.save_run("billing", "You classify billing requests.", "Refund my order",
                   "Totally unrelated response about cooking", "gpt-4o-mini",
                   passed=False, score=0.1, failure_reasons=[])
    golden = store.get_golden("billing", "Refund my order")
    run = store.get_last_run("billing", "Refund my order")
    d = diff_run(golden, run, "You classify billing requests.", regression_threshold=0.80)
    assert d.is_regression


def test_format_diff_returns_string(populated_store):
    golden = populated_store.get_golden("billing", "Refund my order")
    run = populated_store.get_last_run("billing", "Refund my order")
    d = diff_run(golden, run, "You classify billing requests.")
    output = format_diff(d, color=False)
    assert isinstance(output, str)
    assert "billing" in output
    assert "PASS" in output or "REGRESSION" in output
