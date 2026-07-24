"""Citation binder (TG 02.2.2 + 02.2.3, extended in TG 03.3).

Maps extraction output back to pre-extracted per-sentence citation data in a
``ParsedDraft``, producing ``ClaimRecord`` objects. Two entry points:

- ``bind_citations(verdicts, draft)`` — the original Phase 01/02 path, where
  the caller already has web ``Verdict``s (verdict carries claim identity).
- ``bind_extracted_claims(validated_claims, draft)`` — the heavy pipeline
  path (TG 03.3), which starts from ``ValidatedClaim``s straight out of the
  Claimify extractor, *before* any web verification. These records carry
  identity in ``ClaimRecord.claim`` and leave ``web_verdict`` None — no fake
  web result is fabricated (see the ClaimRecord docstring).

Both key on ``original_index`` — the sentence index assigned during
extraction. Multiple claims may share the same ``original_index`` (a single
sentence decomposed into several claims); they all inherit the same citation
data (union semantics). Neither binder populates ``route_verdicts`` or
``suggested_action`` — those come from later stages.
"""

from typing import List

from claim_extractor.schemas import ValidatedClaim
from claim_verifier.schemas import Verdict
from ingest.draft_types import ParsedDraft
from utils.claim_record import CitationStatus, ClaimRecord, DraftPosition


def bind_citations(verdicts: List[Verdict], parsed_draft: ParsedDraft) -> List[ClaimRecord]:
    """Bind each verdict to its source sentence's citation data.

    For each verdict, look up ``parsed_draft.sentences`` by
    ``verdict.original_index``. If found, the resulting ``ClaimRecord``
    inherits that sentence's citation status, cite set, and character
    offsets. If ``original_index`` is out of range, the record falls back
    to ``CitationStatus.CITATION_FREE`` with no character offsets.
    """
    records: List[ClaimRecord] = []

    for verdict in verdicts:
        index = verdict.original_index
        sentence = (
            parsed_draft.sentences[index]
            if 0 <= index < len(parsed_draft.sentences)
            else None
        )

        if sentence is not None:
            position = DraftPosition(
                sentence_index=index,
                section=parsed_draft.section,
                section_index=parsed_draft.section_index,
                char_start=sentence.char_start,
                char_end=sentence.char_end,
            )
            records.append(
                ClaimRecord(
                    web_verdict=verdict,
                    citation_status=sentence.citation_status,
                    cite_set=sentence.cite_set,
                    position=position,
                )
            )
        else:
            records.append(
                ClaimRecord(
                    web_verdict=verdict,
                    citation_status=CitationStatus.CITATION_FREE,
                    position=DraftPosition(sentence_index=index),
                )
            )

    return records


def bind_extracted_claims(
    validated_claims: List[ValidatedClaim], parsed_draft: ParsedDraft
) -> List[ClaimRecord]:
    """Bind Claimify ``ValidatedClaim``s to their source sentence's citations.

    The heavy pipeline (TG 03.3) entry point: identical citation-lookup
    semantics to ``bind_citations`` but keyed off ``ValidatedClaim`` instead
    of ``Verdict``. Each record carries claim identity in ``claim`` and leaves
    ``web_verdict`` None — verification (vault, then web) fills the rest in
    later. An ``original_index`` out of range falls back to
    ``CitationStatus.CITATION_FREE`` with no character offsets.
    """
    records: List[ClaimRecord] = []

    for claim in validated_claims:
        index = claim.original_index
        sentence = (
            parsed_draft.sentences[index]
            if 0 <= index < len(parsed_draft.sentences)
            else None
        )

        if sentence is not None:
            position = DraftPosition(
                sentence_index=index,
                section=parsed_draft.section,
                section_index=parsed_draft.section_index,
                char_start=sentence.char_start,
                char_end=sentence.char_end,
            )
            records.append(
                ClaimRecord(
                    claim=claim,
                    web_verdict=None,
                    citation_status=sentence.citation_status,
                    cite_set=sentence.cite_set,
                    position=position,
                )
            )
        else:
            records.append(
                ClaimRecord(
                    claim=claim,
                    web_verdict=None,
                    citation_status=CitationStatus.CITATION_FREE,
                    position=DraftPosition(sentence_index=index),
                )
            )

    return records
