"""Dispatch claims node - distributes claims for parallel verification.

Sends each claim to a separate verification process.
"""

import logging
from typing import List

from langgraph.graph import END
from langgraph.graph.state import Send

from fact_checker.schemas import State

logger = logging.getLogger(__name__)


def dispatch_claims_for_verification(state: State) -> List[Send] | str:
    """Dispatch extracted claims for parallel verification.

    Args:
        state: Current workflow state

    Returns:
        Either a list of Send objects or END
    """
    claims = state.extracted_claims

    if not claims:
        logger.warning("No claims to verify, ending process")
        return END

    logger.info(f"Dispatching {len(claims)} claims for parallel verification")

    # Create Send objects for each claim to be verified in parallel
    return [Send("claim_verifier", {"claim": claim}) for claim in claims]
