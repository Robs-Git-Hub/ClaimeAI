"""Extract claims node for fact checker."""

import logging
from typing import Any, Dict

from claim_extractor import graph as claim_extractor_graph

from fact_checker.schemas import State

logger = logging.getLogger(__name__)


async def extract_claims(state: State) -> Dict[str, Any]:
    """Extract claims from the answer text.

    Args:
        state: Current workflow state containing text to extract claims from

    Returns:
        Dictionary with extracted_claims key
    """
    logger.info("Starting claim extraction process")

    extractor_payload = {"answer_text": state.answer}

    try:
        extractor_result = await claim_extractor_graph.ainvoke(extractor_payload)
        validated_claims = extractor_result.get("validated_claims", [])
        logger.info(f"Extracted {len(validated_claims)} validated claims")
        return {"extracted_claims": validated_claims}
    except Exception as e:
        logger.error(f"Claim extraction failed: {e}")
        # Return empty list so the pipeline can continue
        return {"extracted_claims": []}
