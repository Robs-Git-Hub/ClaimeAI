"""Citation binder (TG 02.2.2 + 02.2.3).

Maps pipeline-output ``Verdict``s back to pre-extracted per-sentence
citation data in a ``ParsedDraft``, producing ``ClaimRecord`` objects.

Verdicts carry ``original_index`` — the sentence index assigned during
extraction. Multiple claims may share the same ``original_index`` (a single
sentence decomposed into several claims); they all inherit the same
citation data (union semantics). The binder does not populate
``vault_verdicts`` or ``suggested_action`` — those come from later TGs.
"""

from typing import List

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
