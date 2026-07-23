import logging

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from fact_checker.nodes import (
    claim_verifier_node,
    dispatch_claims_for_verification,
    extract_claims,
    generate_report_node,
)
from fact_checker.schemas import State

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_graph() -> CompiledStateGraph:
    """Set up the main fact checker workflow graph.

    The pipeline follows these steps:
    1. Extract claims from input text
    2. Distribute claims for parallel verification
    3. Generate final report
    """
    workflow = StateGraph(State)

    # Add nodes
    workflow.add_node("extract_claims", extract_claims)
    workflow.add_node("claim_verifier", claim_verifier_node)
    workflow.add_node("generate_report_node", generate_report_node)

    # Set entry point
    workflow.set_entry_point("extract_claims")

    # Connect the nodes in sequence
    workflow.add_conditional_edges(
        "extract_claims", dispatch_claims_for_verification, ["claim_verifier", END]
    )
    workflow.add_edge("claim_verifier", "generate_report_node")

    # Set finish point
    workflow.set_finish_point("generate_report_node")

    return workflow.compile()


graph = create_graph()
