"""Claim verifier node - processes a single claim through verification.

Interfaces with the claim verifier subsystem to check factual accuracy.
"""

import logging
from typing import Dict

from claim_verifier import Verdict
from claim_verifier import graph as claim_verifier_graph

logger = logging.getLogger(__name__)


async def claim_verifier_node(inputs: Dict) -> Dict[str, Verdict]:
    """Process a single claim through the claim verifier.

    Args:
        inputs: Dictionary with the claim to verify

    Returns:
        Dictionary with verdict key
    """
    claim = inputs.get("claim")
    if not claim:
        logger.warning("No claim provided to verifier")
        return {}

    logger.info(f"Verifying claim: '{claim.claim_text}'")

    verifier_payload = {"claim": claim}

    try:
        verifier_result = await claim_verifier_graph.ainvoke(verifier_payload)
        verdict = verifier_result.get("verdict")

        if verdict:
            logger.info(f"Verdict for '{claim.claim_text}': {verdict.result}")
            return {"verification_results": [verdict]}
        else:
            logger.warning(f"No verdict returned for claim: '{claim.claim_text}'")
            return {}
    except Exception as e:
        logger.error(f"Error in claim verification: {str(e)}")
        return {}
