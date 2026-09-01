"""
Unit tests for the pure scoring logic in scripts/eval_runner.py -- no network,
no OpenAI key needed. The eval's own metrics need to be trustworthy, or the
numbers it produces are worse than having no eval at all.
"""
from scripts.eval_fixtures import CASES, TENANT_ID
from scripts.eval_runner import CaseResult, UsageTotals, _grounding_check, _percentile, summarize


def test_percentile_basic():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(values, 50) == 30.0
    assert _percentile(values, 0) == 10.0
    assert _percentile(values, 100) == 50.0


def test_percentile_empty_list_is_zero():
    assert _percentile([], 50) == 0.0


def test_grounding_check_flags_product_mentioned_but_not_retrieved():
    all_names = ["Vital C Serum 30ml", "Tinolvital Serum 30ml"]
    answer = "I'd recommend the Tinolvital Serum 30ml for your concern."
    flagged = _grounding_check(answer, sources=[], all_product_names=all_names)
    assert flagged == ["Tinolvital Serum 30ml"]


def test_grounding_check_does_not_flag_retrieved_sources():
    all_names = ["Vital C Serum 30ml", "Tinolvital Serum 30ml"]
    answer = "I'd recommend the Tinolvital Serum 30ml for your concern."
    flagged = _grounding_check(answer, sources=["Tinolvital Serum 30ml"], all_product_names=all_names)
    assert flagged == []


def test_summarize_computes_mean_precision_and_recall():
    results = [
        CaseResult(
            case_id="a", query="q1", expected_products=["X"], expect_no_match=False,
            retrieved_products=["X", "Y"], precision_at_k=0.5, recall=1.0,
        ),
        CaseResult(
            case_id="b", query="q2", expected_products=["Z"], expect_no_match=False,
            retrieved_products=["Y"], precision_at_k=0.0, recall=0.0,
        ),
    ]
    summary = summarize(results, UsageTotals())
    assert summary["retrieval"]["mean_precision_at_k"] == 0.25
    assert summary["retrieval"]["mean_recall"] == 0.5
    assert summary["retrieval"]["cases_scored"] == 2


def test_summarize_tracks_no_match_rejection():
    results = [
        CaseResult(case_id="c", query="q3", expected_products=[], expect_no_match=True, correctly_rejected=True),
        CaseResult(case_id="d", query="q4", expected_products=[], expect_no_match=True, correctly_rejected=False),
    ]
    summary = summarize(results, UsageTotals())
    assert summary["no_match_handling"]["cases"] == 2
    assert summary["no_match_handling"]["correctly_rejected"] == 1


def test_usage_totals_estimated_cost_is_positive_for_nonzero_usage():
    totals = UsageTotals(embedding_tokens=1000, chat_prompt_tokens=1000, chat_completion_tokens=1000)
    assert totals.estimated_cost_usd() > 0


def test_fixtures_are_internally_consistent():
    assert TENANT_ID == "farmacia_carmen_sanjuan"
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    for case in CASES:
        assert case.query, f"case {case.id} has an empty query"
        assert case.expect_no_match or case.expected_products, (
            f"case {case.id} must either expect no match or declare expected_products"
        )
