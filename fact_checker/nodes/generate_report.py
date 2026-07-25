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

    # Count claims by verification result. Cover every VerificationResult
    # member (not just Supported/Refuted) so Insufficient/Conflicting
    # verdicts are counted instead of silently dropped from the summary.
    result_counts = {result: 0 for result in VerificationResult}

    for verdict in state.verification_results:
        logger.info(f"Verdict for '{verdict.claim_text}': {verdict.result}")
        result_counts[verdict.result] += 1

    # Generate summary text. Insufficient/Conflicting are only mentioned
    # when nonzero, keeping the common-case message unchanged.
    summary_parts = [
        f"{result_counts[VerificationResult.SUPPORTED]} supported",
        f"{result_counts[VerificationResult.REFUTED]} refuted",
    ]
    if result_counts[VerificationResult.INSUFFICIENT]:
        summary_parts.append(
            f"{result_counts[VerificationResult.INSUFFICIENT]} insufficient"
        )
    if result_counts[VerificationResult.CONFLICTING]:
        summary_parts.append(
            f"{result_counts[VerificationResult.CONFLICTING]} conflicting"
        )
    summary = (
        f"Fact-check complete. Of {len(state.verification_results)} claims verified: "
        + ", ".join(summary_parts)
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
