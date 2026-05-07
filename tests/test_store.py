import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from prompt_sentinel.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(root=str(tmp_path))


def test_save_and_get_golden(store):
    store.save_golden("suite_a", "You are helpful.", "What is 2+2?", "4", "gpt-4o-mini")
    g = store.get_golden("suite_a", "What is 2+2?")
    assert g is not None
    assert g.name == "suite_a"
    assert g.golden_output == "4"
    assert g.model == "gpt-4o-mini"
    assert len(g.prompt_sha) == 16


def test_golden_overwrites_on_same_name_input(store):
    store.save_golden("suite_a", "Prompt v1", "input", "output v1", "gpt-4o-mini")
    store.save_golden("suite_a", "Prompt v2", "input", "output v2", "gpt-4o-mini")
    g = store.get_golden("suite_a", "input")
    assert g.golden_output == "output v2"


def test_get_golden_returns_none_if_missing(store):
    g = store.get_golden("nonexistent", "input")
    assert g is None


def test_save_and_get_run(store):
    store.save_golden("suite_b", "Prompt", "Hello", "Hi there", "gpt-4o-mini")
    store.save_run("suite_b", "Prompt", "Hello", "Hello back", "gpt-4o-mini",
                   passed=True, score=0.9, failure_reasons=[])
    r = store.get_last_run("suite_b", "Hello")
    assert r is not None
    assert r.actual_output == "Hello back"
    assert r.passed is True
    assert r.score == 0.9


def test_list_names(store):
    store.save_golden("alpha", "P", "i", "o", "gpt-4o-mini")
    store.save_golden("beta", "P", "i", "o", "gpt-4o-mini")
    names = store.list_names()
    assert "alpha" in names
    assert "beta" in names


def test_multiple_goldens_per_suite(store):
    store.save_golden("suite_c", "P", "input 1", "output 1", "gpt-4o-mini")
    store.save_golden("suite_c", "P", "input 2", "output 2", "gpt-4o-mini")
    goldens = store.get_goldens("suite_c")
    assert len(goldens) == 2


def test_run_failure_reasons(store):
    store.save_golden("suite_d", "P", "i", "o", "gpt-4o-mini")
    store.save_run("suite_d", "P", "i", "bad output", "gpt-4o-mini",
                   passed=False, score=0.2, failure_reasons=["Missing keyword", "Too short"])
    r = store.get_last_run("suite_d", "i")
    assert r.failure_reasons == ["Missing keyword", "Too short"]
