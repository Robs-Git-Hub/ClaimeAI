"""Tests for the citation binder (TG 02.2.2 + 02.2.3).

The binder maps pipeline-output Verdicts (keyed by ``original_index``) back
to pre-extracted per-sentence citation data in a ``ParsedDraft``, producing
``ClaimRecord`` objects. See ingest/citation_binder.py.

Test fixtures are constructed manually rather than imported from
``ingest.draft_parser`` (built by another agent in parallel).
"""

from claim_verifier.schemas import Verdict, VerificationResult
from ingest.citation_binder import bind_citations
from ingest.draft_types import ParsedDraft, ParsedSentence
from utils.claim_record import CitationStatus


def make_verdict(claim_text, original_index, result=VerificationResult.SUPPORTED):
    return Verdict(
        claim_text=claim_text,
        disambiguated_sentence=claim_text,
        original_sentence=claim_text,
        original_index=original_index,
        result=result,
        reasoning="Test reasoning",
        sources=[],
    )


def make_sentence(index, text, citation_status=CitationStatus.CITATION_FREE, cite_set=None, unparsed=None):
    return ParsedSentence(
        sentence_index=index,
        original_text=text,
        clean_text=text,
        citation_status=citation_status,
        cite_set=cite_set or [],
        unparsed_citations=unparsed or [],
        char_start=0,
        char_end=len(text),
    )


def make_draft(sentences, section=None, section_index=None, original_text=None, clean_text=None):
    text = original_text if original_text is not None else " ".join(s.original_text for s in sentences)
    ctext = clean_text if clean_text is not None else " ".join(s.clean_text for s in sentences)
    return ParsedDraft(
        original_text=text,
        clean_text=ctext,
        sentences=sentences,
        section=section,
        section_index=section_index,
    )


# ---------------------------------------------------------------------------
# Basic mapping
# ---------------------------------------------------------------------------


def test_single_claim_maps_to_sentence():
    sentence = make_sentence(0, "The sky is blue.")
    draft = make_draft([sentence])
    verdict = make_verdict("The sky is blue.", 0)

    records = bind_citations([verdict], draft)

    assert len(records) == 1
    record = records[0]
    assert record.web_verdict is verdict
    assert record.citation_status == CitationStatus.CITATION_FREE
    assert record.cite_set == []
    assert record.position.sentence_index == 0


def test_cited_claim_inherits_cite_set():
    sentence = make_sentence(0, "Text.", citation_status=CitationStatus.CITED, cite_set=["SOURCE-a"])
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].cite_set == ["SOURCE-a"]
    assert records[0].citation_status == CitationStatus.CITED


def test_citation_free_claim():
    sentence = make_sentence(0, "Text.", citation_status=CitationStatus.CITATION_FREE)
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].citation_status == CitationStatus.CITATION_FREE


def test_unparsed_citation():
    sentence = make_sentence(
        0, "Text (Smith 2020).",
        citation_status=CitationStatus.UNPARSED_CITATION,
        unparsed=["Smith 2020"],
    )
    draft = make_draft([sentence])
    verdict = make_verdict("Text (Smith 2020).", 0)

    records = bind_citations([verdict], draft)

    assert records[0].citation_status == CitationStatus.UNPARSED_CITATION


def test_multi_cite_union_semantics():
    sentence = make_sentence(
        0, "Text.", citation_status=CitationStatus.CITED, cite_set=["SOURCE-a", "SOURCE-b"]
    )
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].cite_set == ["SOURCE-a", "SOURCE-b"]


# ---------------------------------------------------------------------------
# Decomposition (multiple claims sharing one sentence index)
# ---------------------------------------------------------------------------


def test_decomposed_claims_share_citations():
    sentence = make_sentence(
        0, "Text.", citation_status=CitationStatus.CITED, cite_set=["SOURCE-a", "SOURCE-b"]
    )
    draft = make_draft([sentence])
    verdict_1 = make_verdict("Claim one.", 0)
    verdict_2 = make_verdict("Claim two.", 0)

    records = bind_citations([verdict_1, verdict_2], draft)

    assert len(records) == 2
    assert records[0].cite_set == ["SOURCE-a", "SOURCE-b"]
    assert records[1].cite_set == ["SOURCE-a", "SOURCE-b"]
    assert records[0].citation_status == CitationStatus.CITED
    assert records[1].citation_status == CitationStatus.CITED


def test_multiple_sentences_multiple_verdicts():
    sentences = [
        make_sentence(0, "First.", citation_status=CitationStatus.CITATION_FREE),
        make_sentence(1, "Second.", citation_status=CitationStatus.CITED, cite_set=["SOURCE-x"]),
        make_sentence(2, "Third.", citation_status=CitationStatus.UNPARSED_CITATION, unparsed=["Jones 2019"]),
    ]
    draft = make_draft(sentences)
    verdicts = [
        make_verdict("First.", 0),
        make_verdict("Second.", 1),
        make_verdict("Third.", 2),
    ]

    records = bind_citations(verdicts, draft)

    assert len(records) == 3
    assert records[0].citation_status == CitationStatus.CITATION_FREE
    assert records[0].cite_set == []
    assert records[1].citation_status == CitationStatus.CITED
    assert records[1].cite_set == ["SOURCE-x"]
    assert records[2].citation_status == CitationStatus.UNPARSED_CITATION


# ---------------------------------------------------------------------------
# Position / section metadata
# ---------------------------------------------------------------------------


def test_position_populated_correctly():
    padding = [make_sentence(i, f"Padding {i}.") for i in range(3)]
    sentence = ParsedSentence(
        sentence_index=3,
        original_text="Some text here.",
        clean_text="Some text here.",
        citation_status=CitationStatus.CITATION_FREE,
        cite_set=[],
        unparsed_citations=[],
        char_start=120,
        char_end=180,
    )
    draft = make_draft(padding + [sentence], section="Introduction", section_index=0)
    verdict = make_verdict("Some text here.", 3)

    records = bind_citations([verdict], draft)

    position = records[0].position
    assert position.sentence_index == 3
    assert position.section == "Introduction"
    assert position.section_index == 0
    assert position.char_start == 120
    assert position.char_end == 180


def test_section_metadata_from_parsed_draft():
    sentences = [
        make_sentence(0, "First."),
        make_sentence(1, "Second."),
    ]
    draft = make_draft(sentences, section="Introduction", section_index=0)
    verdicts = [make_verdict("First.", 0), make_verdict("Second.", 1)]

    records = bind_citations(verdicts, draft)

    for record in records:
        assert record.position.section == "Introduction"
        assert record.position.section_index == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_out_of_range_index_graceful():
    sentences = [make_sentence(0, "A."), make_sentence(1, "B."), make_sentence(2, "C.")]
    draft = make_draft(sentences, section="Introduction", section_index=0)
    verdict = make_verdict("Out of range claim.", 99)

    records = bind_citations([verdict], draft)

    assert len(records) == 1
    record = records[0]
    assert record.citation_status == CitationStatus.CITATION_FREE
    assert record.cite_set == []
    assert record.position.sentence_index == 99
    assert record.position.char_start is None
    assert record.position.char_end is None


def test_empty_verdicts():
    draft = make_draft([make_sentence(0, "A.")])

    records = bind_citations([], draft)

    assert records == []


def test_empty_sentences():
    draft = make_draft([])
    verdicts = [make_verdict("A.", 0), make_verdict("B.", 1)]

    records = bind_citations(verdicts, draft)

    assert len(records) == 2
    for record in records:
        assert record.citation_status == CitationStatus.CITATION_FREE
        assert record.cite_set == []


def test_web_verdict_preserved():
    sentence = make_sentence(0, "Text.")
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].web_verdict is verdict


def test_route_verdicts_empty_by_default():
    sentence = make_sentence(0, "Text.")
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].route_verdicts == []


def test_suggested_action_none_by_default():
    sentence = make_sentence(0, "Text.")
    draft = make_draft([sentence])
    verdict = make_verdict("Text.", 0)

    records = bind_citations([verdict], draft)

    assert records[0].suggested_action is None
