"""Generate report node - creates a comprehensive fact-check report.

Compiles verification results into a final report with summary.
"""

import logging
from datetime import datetime
from typing import Dict

from claim_verifier.schemas import VerificationResult
from fact_checker.schemas import FactCheckReport, State

logger = logging.getLogger(__name__)


async def generate_report_node(state: State) -> Dict[str, FactCheckReport]:
    """Generate the final fact-checking report.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with final_report key
    """
    logger.info("Generating final fact-check report")

    # Count claims by verification result
    result_counts = {
        VerificationResult.SUPPORTED: 0,
        VerificationResult.REFUTED: 0,
    }

    for verdict in state.verification_results:
        if verdict.result in result_counts:
            logger.info(f"Verdict for '{verdict.claim_text}': {verdict.result}")
            result_counts[verdict.result] += 1

    # Generate summary text
    summary = (
        f"Fact-check complete. Of {len(state.verification_results)} claims verified: "
        f"{result_counts[VerificationResult.SUPPORTED]} supported, "
        f"{result_counts[VerificationResult.REFUTED]} refuted"
    )

    # Create the final report
    report = FactCheckReport(
        answer=state.answer,
        claims_verified=len(state.verification_results),
        verified_claims=state.verification_results,
        summary=summary,
        timestamp=datetime.now(),
    )

    logger.info(f"Report generated: {summary}")
    return {"final_report": report}
