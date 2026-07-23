"""Retrieve evidence node - fetches evidence for claims using Exa AI Search.

Uses search queries to retrieve relevant evidence snippets from the web using neural search.
"""

import logging
from typing import Any, Dict, List

from langchain_exa import ExaSearchRetriever
from langchain_tavily import TavilySearch

from claim_verifier.config import EVIDENCE_RETRIEVAL_CONFIG
from claim_verifier.schemas import ClaimVerifierState, Evidence

logger = logging.getLogger(__name__)

# Retrieval settings
RESULTS_PER_QUERY = EVIDENCE_RETRIEVAL_CONFIG["results_per_query"]
SEARCH_PROVIDER = EVIDENCE_RETRIEVAL_CONFIG["search_provider"]


class SearchProviders:
    @staticmethod
    async def exa(query: str) -> List[Evidence]:
        logger.info(f"Searching with Exa: '{query}'")

        try:
            retriever = ExaSearchRetriever(
                k=RESULTS_PER_QUERY,
                text_contents_options={"max_characters": 2000},
                type="neural",
            )

            results = await retriever.ainvoke(query)

            evidence = [
                Evidence(
                    url=doc.metadata.get("url", ""),
                    text=doc.page_content[:2000],
                    title=doc.metadata.get("title"),
                )
                for doc in results
            ]

            logger.info(f"Retrieved {len(evidence)} evidence items")
            return evidence

        except Exception as e:
            logger.error(f"Exa search failed for '{query}': {e}")
            return []

    @staticmethod
    async def tavily(query: str) -> List[Evidence]:
        logger.info(f"Searching with Tavily: '{query}'")

        try:
            search = TavilySearch(
                max_results=RESULTS_PER_QUERY,
                topic="general",
                include_raw_content="markdown",
            )

            results = await search.ainvoke(query)
            evidence = SearchProviders._parse_tavily_results(results)

            logger.info(f"Retrieved {len(evidence)} evidence items")
            return evidence

        except Exception as e:
            logger.error(f"Tavily search failed for '{query}': {e}")
            return []

    @staticmethod
    def _parse_tavily_results(results: Any) -> List[Evidence]:
        match results:
            case {"results": search_results} if isinstance(search_results, list):
                return [
                    Evidence(
                        url=result.get("url", ""),
                        text=result.get("raw_content") or result.get("content", ""),
                        title=result.get("title", ""),
                    )
                    for result in search_results
                    if isinstance(result, dict)
                ]
            case str():
                return [Evidence(url="", text=results, title="Tavily Search Result")]
            case _:
                return []


async def _search_query(query: str) -> List[Evidence]:
    match SEARCH_PROVIDER.lower():
        case "tavily":
            return await SearchProviders.tavily(query)
        case _:
            return await SearchProviders.exa(query)


async def retrieve_evidence_node(
    state: ClaimVerifierState,
) -> Dict[str, List[Evidence]]:
    if not state.query:
        logger.warning("No search query to process")
        return {"evidence": []}

    evidence = await _search_query(state.query)
    logger.info(f"Retrieved {len(evidence)} total evidence snippets")

    return {"evidence": [item.model_dump() for item in evidence]}
