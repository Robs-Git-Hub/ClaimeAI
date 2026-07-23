"""Search cost tracking for fact-checking runs.

Counts search API calls per provider and estimates costs based on
published per-call pricing. Free-tier balance is estimated from
monthly allowances minus current-run usage.

The langchain search wrappers (ExaSearchRetriever, TavilySearch) do not
expose response metadata like usage stats or remaining credits, so this
module is deliberately call-count-based rather than reading real usage
from the API responses.

Note: this module uses process-local counters. When the pipeline runs
inside the LangGraph dev server, counters accumulate in the server
process — search costs are logged at INFO level via the ``logging``
module and visible in the server's terminal output. The ``print_summary``
function is for direct (in-process) invocation only.

Pricing (as of 2026-07):
  Exa:    $0.007 per search ($10/month free credit; new accounts also
          get a one-time $20 starter credit)
  Tavily: 1 credit per search (1,000 free credits/month)
"""

import logging

logger = logging.getLogger(__name__)

_counters: dict[str, int] = {"exa": 0, "tavily": 0}

COST_PER_SEARCH: dict[str, float] = {
    "exa": 0.007,
    "tavily": 0.008,
}

FREE_TIER: dict[str, dict] = {
    "exa": {"monthly_credit_usd": 10.0},
    "tavily": {"monthly_credits": 1000, "cost_per_credit_usd": 0.008},
}


def record_search(provider: str) -> None:
    """Increment the call counter for a search provider (case-insensitive)."""
    key = provider.lower()
    if key not in _counters:
        _counters[key] = 0
    _counters[key] += 1
    cost = COST_PER_SEARCH.get(key, 0.0)
    logger.info(
        "search_cost: provider=%s total=%d est_cost=$%.4f",
        key, _counters[key], _counters[key] * cost,
    )


def get_summary() -> dict:
    """Return a summary of search counts, estimated cost, and free-tier balance."""
    searches = dict(_counters)
    estimated_cost = sum(
        count * COST_PER_SEARCH.get(provider, 0.0)
        for provider, count in searches.items()
    )

    exa_count = searches.get("exa", 0)
    exa_credit = FREE_TIER["exa"]["monthly_credit_usd"]
    exa_cost_per_search = COST_PER_SEARCH["exa"]
    exa_remaining_usd = exa_credit - exa_count * exa_cost_per_search
    exa_remaining_searches = exa_remaining_usd / exa_cost_per_search

    tavily_count = searches.get("tavily", 0)
    tavily_credits = FREE_TIER["tavily"]["monthly_credits"]

    free_tier = {
        "exa": {
            "remaining_usd": exa_remaining_usd,
            "remaining_searches": exa_remaining_searches,
        },
        "tavily": {
            "remaining_credits": tavily_credits - tavily_count,
        },
    }

    return {
        "searches": searches,
        "estimated_cost": estimated_cost,
        "free_tier": free_tier,
    }


def reset() -> None:
    """Clear all search counters back to zero."""
    for key in _counters:
        _counters[key] = 0


def print_summary() -> None:
    """Print a formatted search cost summary to stdout."""
    summary = get_summary()
    searches = summary["searches"]
    free_tier = summary["free_tier"]

    print("\n=== Search cost summary ===")
    for provider, count in searches.items():
        print(f"  {provider}: {count} search(es)")
    print(f"  Estimated cost: ${summary['estimated_cost']:.4f}")
    print("  Free-tier remaining (estimated, this run only):")
    print(
        f"    exa:    ${free_tier['exa']['remaining_usd']:.2f} "
        f"(~{free_tier['exa']['remaining_searches']:.0f} searches)"
    )
    print(f"    tavily: {free_tier['tavily']['remaining_credits']} credits")
    print("============================\n")
