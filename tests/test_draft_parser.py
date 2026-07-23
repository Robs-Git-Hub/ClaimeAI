"""Tests for the draft parser (TG 02.2.1 + 02.2.4).

Covers wikilink parsing, author-year detection, sentence splitting
(replicating claim_extractor's sentence_splitter logic), and the
parse_draft() entry point that ties them together.
"""

from ingest.draft_parser import (
    detect_author_year,
    parse_draft,
    parse_wikilinks,
    split_sentences,
    strip_wikilinks,
)
from utils.claim_record import CitationStatus


# ---------------------------------------------------------------------------
# parse_wikilinks
# ---------------------------------------------------------------------------


class TestParseWikilinks:
    def test_parse_wikilinks_single(self):
        text = "[[SOURCE-a|A (2025)]]"
        result = parse_wikilinks(text)
        assert len(result) == 1
        wl = result[0]
        assert wl.target == "SOURCE-a"
        assert wl.display == "A (2025)"
        assert wl.char_start == 0
        assert wl.char_end == len(text)

    def test_parse_wikilinks_multiple(self):
        text = "See [[SOURCE-a|A (2025)]] and [[SOURCE-b|B (2024)]]."
        result = parse_wikilinks(text)
        assert len(result) == 2
        assert result[0].target == "SOURCE-a"
        assert result[0].display == "A (2025)"
        assert result[1].target == "SOURCE-b"
        assert result[1].display == "B (2024)"

    def test_parse_wikilinks_no_pipe(self):
        text = "[[NOTE-NAME]]"
        result = parse_wikilinks(text)
        assert len(result) == 1
        assert result[0].target == "NOTE-NAME"
        assert result[0].display == "NOTE-NAME"

    def test_parse_wikilinks_empty_text(self):
        assert parse_wikilinks("") == []


# ---------------------------------------------------------------------------
# strip_wikilinks
# ---------------------------------------------------------------------------


class TestStripWikilinks:
    def test_strip_wikilinks(self):
        assert strip_wikilinks("[[SOURCE-a|A (2025)]]") == "A (2025)"

    def test_strip_wikilinks_no_pipe(self):
        assert strip_wikilinks("[[NOTE-NAME]]") == "NOTE-NAME"

    def test_strip_preserves_sentence_structure(self):
        text = "This claim is supported [[SOURCE-a|A (2025)]]."
        stripped = strip_wikilinks(text)
        assert "[[" not in stripped
        assert "]]" not in stripped
        assert stripped == "This claim is supported A (2025)."


# ---------------------------------------------------------------------------
# detect_author_year
# ---------------------------------------------------------------------------


class TestDetectAuthorYear:
    def test_detect_author_year_basic(self):
        assert detect_author_year("Evidence shows this (Zeng 2026).") == [
            "(Zeng 2026)"
        ]

    def test_detect_author_year_with_comma(self):
        assert detect_author_year("Evidence (Zeng, 2026) supports this.") == [
            "(Zeng, 2026)"
        ]

    def test_detect_author_year_with_ampersand(self):
        assert detect_author_year("(Smith & Jones 2024)") == ["(Smith & Jones 2024)"]

    def test_detect_author_year_et_al(self):
        assert detect_author_year("(Smith et al. 2024)") == ["(Smith et al. 2024)"]

    def test_detect_author_year_no_match(self):
        assert detect_author_year("Plain text with no citations at all.") == []


# ---------------------------------------------------------------------------
# split_sentences
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_split_sentences_basic(self):
        text = "This is one sentence. This is another sentence."
        result = split_sentences(text)
        assert len(result) == 2
        assert result[0] == "This is one sentence."
        assert result[1] == "This is another sentence."

    def test_split_sentences_paragraphs(self):
        text = "Paragraph one sentence.\nParagraph two sentence."
        result = split_sentences(text)
        assert len(result) == 2
        assert "Paragraph one sentence." in result
        assert "Paragraph two sentence." in result

    def test_split_sentences_merge_short_fragments(self):
        text = "Yes. This is the full follow-up sentence."
        result = split_sentences(text)
        # "Yes." (4 chars) is < 5 chars and gets merged into the next sentence.
        assert len(result) == 1
        assert "Yes." in result[0]
        assert "This is the full follow-up sentence." in result[0]


# ---------------------------------------------------------------------------
# parse_draft
# ---------------------------------------------------------------------------


class TestParseDraft:
    def test_parse_draft_citation_free(self):
        text = "This is a plain sentence. This is another one."
        draft = parse_draft(text)
        assert len(draft.sentences) == 2
        for sentence in draft.sentences:
            assert sentence.citation_status == CitationStatus.CITATION_FREE
            assert sentence.cite_set == []
            assert sentence.unparsed_citations == []

    def test_parse_draft_with_wikilinks(self):
        text = "This claim is supported by evidence [[SOURCE-a|A (2025)]]."
        draft = parse_draft(text)
        assert len(draft.sentences) == 1
        sentence = draft.sentences[0]
        assert sentence.citation_status == CitationStatus.CITED
        assert sentence.cite_set == ["SOURCE-a"]

    def test_parse_draft_mixed(self):
        text = (
            "This is cited [[SOURCE-a|A (2025)]]. This is not cited at all."
        )
        draft = parse_draft(text)
        assert len(draft.sentences) == 2
        assert draft.sentences[0].citation_status == CitationStatus.CITED
        assert draft.sentences[0].cite_set == ["SOURCE-a"]
        assert draft.sentences[1].citation_status == CitationStatus.CITATION_FREE
        assert draft.sentences[1].cite_set == []

    def test_parse_draft_multi_cite_sentence(self):
        text = (
            "This claim cites two sources [[SOURCE-a|A (2025)]] "
            "and [[SOURCE-b|B (2024)]]."
        )
        draft = parse_draft(text)
        assert len(draft.sentences) == 1
        assert draft.sentences[0].cite_set == ["SOURCE-a", "SOURCE-b"]
        assert draft.sentences[0].citation_status == CitationStatus.CITED

    def test_parse_draft_unparsed_citation(self):
        text = "This finding is notable (Zeng 2026)."
        draft = parse_draft(text)
        assert len(draft.sentences) == 1
        sentence = draft.sentences[0]
        assert sentence.citation_status == CitationStatus.UNPARSED_CITATION
        assert sentence.unparsed_citations == ["(Zeng 2026)"]
        assert sentence.cite_set == []

    def test_parse_draft_section_metadata(self):
        draft = parse_draft("Some text.", section="Intro", section_index=0)
        assert draft.section == "Intro"
        assert draft.section_index == 0

    def test_parse_draft_clean_text_matches_strip(self):
        text = "This claim is supported [[SOURCE-a|A (2025)]]."
        draft = parse_draft(text)
        assert draft.clean_text == strip_wikilinks(text)

    def test_sentence_index_stability(self):
        text = (
            "This claim is supported [[SOURCE-a|A (2025)]]. "
            "This is another sentence [[SOURCE-b|B (2024)]]."
        )
        original_sentences = split_sentences(text)
        stripped_sentences = split_sentences(strip_wikilinks(text))
        assert len(original_sentences) == len(stripped_sentences)

    def test_parse_draft_sentence_positions(self):
        text = "First sentence here. Second sentence here."
        draft = parse_draft(text)
        for sentence in draft.sentences:
            assert (
                text[sentence.char_start : sentence.char_end]
                == sentence.original_text
            )

    def test_trailing_citation_scope_sentence_only(self):
        text = (
            "Earlier statement without citation. "
            "Later statement with citation [[SOURCE-a|A (2025)]]."
        )
        draft = parse_draft(text)
        assert len(draft.sentences) == 2
        assert draft.sentences[0].cite_set == []
        assert draft.sentences[0].citation_status == CitationStatus.CITATION_FREE
        assert draft.sentences[1].cite_set == ["SOURCE-a"]
        assert draft.sentences[1].citation_status == CitationStatus.CITED
