import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from prompt_sentinel.scorer import score, similarity_score


def test_contains_pass():
    s, results = score("Your refund has been processed.", [{"contains": "refund"}])
    assert s == 1.0
    assert results[0].passed

def test_contains_fail():
    s, results = score("Order confirmed.", [{"contains": "refund"}])
    assert s == 0.0
    assert not results[0].passed

def test_not_contains_pass():
    s, results = score("Order confirmed.", [{"not_contains": "error"}])
    assert s == 1.0

def test_not_contains_fail():
    s, results = score("An error occurred.", [{"not_contains": "error"}])
    assert s == 0.0

def test_exact_pass():
    s, results = score("  hello world  ", [{"exact": "hello world"}])
    assert s == 1.0

def test_exact_fail():
    s, results = score("hello earth", [{"exact": "hello world"}])
    assert s == 0.0

def test_regex_pass():
    s, results = score("Order #12345 processed", [{"regex": r"Order #\d+"}])
    assert s == 1.0

def test_regex_fail():
    s, results = score("No order here", [{"regex": r"Order #\d+"}])
    assert s == 0.0

def test_json_valid_pass():
    s, results = score('{"status": "ok"}', [{"json_valid": True}])
    assert s == 1.0

def test_json_valid_fail():
    s, results = score("not json", [{"json_valid": True}])
    assert s == 0.0

def test_json_schema_pass():
    s, results = score('{"status": "ok", "code": 200}', [{"json_schema": {"status": None, "code": None}}])
    assert s == 1.0

def test_json_schema_fail():
    s, results = score('{"status": "ok"}', [{"json_schema": {"status": None, "missing_key": None}}])
    assert s == 0.0

def test_min_length_pass():
    s, results = score("hello world", [{"min_length": 5}])
    assert s == 1.0

def test_min_length_fail():
    s, results = score("hi", [{"min_length": 100}])
    assert s == 0.0

def test_max_length_pass():
    s, results = score("hi", [{"max_length": 100}])
    assert s == 1.0

def test_starts_with():
    s, _ = score("Refund processed.", [{"starts_with": "Refund"}])
    assert s == 1.0

def test_ends_with():
    s, _ = score("See you later.", [{"ends_with": "later."}])
    assert s == 1.0

def test_multiple_assertions_partial():
    s, results = score(
        "Refund approved.",
        [{"contains": "refund"}, {"contains": "error"}]
    )
    assert s == 0.5
    assert results[0].passed
    assert not results[1].passed

def test_no_assertions_returns_perfect():
    s, results = score("anything", [])
    assert s == 1.0
    assert results == []

def test_similarity_identical():
    assert similarity_score("hello world", "hello world") == 1.0

def test_similarity_empty():
    assert similarity_score("", "") == 1.0
    assert similarity_score("hello", "") == 0.0

def test_similarity_partial():
    s = similarity_score("the quick brown fox", "the quick red fox")
    assert 0.5 < s < 1.0

def test_case_insensitive_contains():
    s, _ = score("REFUND PROCESSED", [{"contains": "refund"}])
    assert s == 1.0
