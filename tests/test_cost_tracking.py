"""Tests for search cost tracking (call-count-based, hardcoded pricing).

No network calls are made: this module just counts search API calls per
provider and estimates cost from published per-call pricing. Tests reset
module state before/after each test to keep counters isolated.
"""

import pytest

import utils.cost_tracking as cost_tracking
from utils.cost_tracking import get_summary, record_search, reset


@pytest.fixture(autouse=True)
def _reset_counters():
    """Ensure every test starts and ends with a clean counter state."""
    reset()
    yield
    reset()


# ---------------------------------------------------------------------------
# record_search
# ---------------------------------------------------------------------------


def test_record_search_exa_increments_counter():
    record_search("exa")
    assert cost_tracking._counters["exa"] == 1


def test_record_search_tavily_increments_counter():
    record_search("tavily")
    assert cost_tracking._counters["tavily"] == 1


def test_record_search_is_case_insensitive():
    record_search("EXA")
    record_search("Tavily")
    assert cost_tracking._counters["exa"] == 1
    assert cost_tracking._counters["tavily"] == 1


def test_multiple_calls_accumulate():
    record_search("exa")
    record_search("exa")
    record_search("exa")
    record_search("tavily")
    record_search("tavily")
    assert cost_tracking._counters["exa"] == 3
    assert cost_tracking._counters["tavily"] == 2


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


def test_get_summary_returns_expected_keys():
    summary = get_summary()
    assert set(summary.keys()) == {"searches", "estimated_cost", "free_tier"}
    assert isinstance(summary["searches"], dict)
    assert isinstance(summary["estimated_cost"], float)
    assert isinstance(summary["free_tier"], dict)


def test_get_summary_on_fresh_state_is_zero():
    summary = get_summary()
    assert summary["searches"] == {"exa": 0, "tavily": 0}
    assert summary["estimated_cost"] == 0.0


def test_get_summary_cost_calculation():
    record_search("exa")
    record_search("exa")
    record_search("tavily")

    summary = get_summary()
    assert summary["searches"] == {"exa": 2, "tavily": 1}
    # 2 * $0.007 + 1 * $0.008 = $0.022
    assert summary["estimated_cost"] == pytest.approx(0.022)


def test_get_summary_free_tier_estimates_exa():
    record_search("exa")
    summary = get_summary()
    free_tier = summary["free_tier"]
    assert "exa" in free_tier
    # $10 monthly credit / $0.007 per search ~= 1428 searches remaining
    # after 1 used this run.
    assert free_tier["exa"]["remaining_searches"] == pytest.approx(
        10.0 / 0.007 - 1, abs=1
    )
    assert free_tier["exa"]["remaining_usd"] == pytest.approx(10.0 - 0.007)


def test_get_summary_free_tier_estimates_tavily():
    record_search("tavily")
    summary = get_summary()
    free_tier = summary["free_tier"]
    assert "tavily" in free_tier
    assert free_tier["tavily"]["remaining_credits"] == 1000 - 1


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_clears_all_counters():
    record_search("exa")
    record_search("tavily")
    reset()
    assert cost_tracking._counters == {"exa": 0, "tavily": 0}


def test_get_summary_after_reset_is_zero():
    record_search("exa")
    record_search("tavily")
    reset()
    summary = get_summary()
    assert summary["searches"] == {"exa": 0, "tavily": 0}
    assert summary["estimated_cost"] == 0.0


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------


def test_print_summary_runs_without_error(capsys):
    record_search("exa")
    record_search("tavily")
    from utils.cost_tracking import print_summary

    print_summary()
    captured = capsys.readouterr()
    assert "exa" in captured.out
    assert "tavily" in captured.out
    assert "$" in captured.out
