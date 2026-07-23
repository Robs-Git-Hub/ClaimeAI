"""Draft parser (TG 02.2.1 + 02.2.4).

Parses a wikilinked markdown draft into sentences with citation metadata,
and detects non-wikilink (plain author-year) citations that slipped
through unparsed.

Public API:
    parse_wikilinks(text)   -> List[WikilinkCitation]
    strip_wikilinks(text)   -> str
    detect_author_year(text) -> List[str]
    split_sentences(text)  -> List[str]
    parse_draft(text, section=None, section_index=None) -> ParsedDraft
"""

import re
from typing import List, Optional, Tuple

import nltk

from claim_extractor.nodes.sentence_splitter import ensure_nltk_resources
from ingest.draft_types import ParsedDraft, ParsedSentence, WikilinkCitation
from utils.claim_record import CitationStatus

__all__ = [
    "parse_wikilinks",
    "strip_wikilinks",
    "detect_author_year",
    "split_sentences",
    "parse_draft",
]

# ---------------------------------------------------------------------------
# Wikilinks: [[SOURCE-slug|Display (Year)]] or [[NOTE-NAME]]
# ---------------------------------------------------------------------------

_WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")

# ---------------------------------------------------------------------------
# Plain author-year citations, e.g. (Zeng 2026), (Smith et al. 2024a)
# ---------------------------------------------------------------------------

_AUTHOR_YEAR_PATTERN = re.compile(
    r"\("
    r"[A-Z][a-zA-Z]+(?:\s+(?:&|and)\s+[A-Z][a-zA-Z]+)*"
    r"(?:,?\s*et\s+al\.?)?"
    r"[,]?\s+\d{4}[a-z]?"
    r"\)"
)


def parse_wikilinks(text: str) -> List[WikilinkCitation]:
    """Extract all `[[target|display]]` and `[[target]]` wikilinks with positions."""
    citations: List[WikilinkCitation] = []
    for match in _WIKILINK_PATTERN.finditer(text):
        target = match.group(1)
        display = match.group(2) if match.group(2) is not None else target
        citations.append(
            WikilinkCitation(
                target=target,
                display=display,
                char_start=match.start(),
                char_end=match.end(),
            )
        )
    return citations


def strip_wikilinks(text: str) -> str:
    """Replace `[[target|display]]` with `display`, and `[[target]]` with `target`."""

    def _replace(match: re.Match) -> str:
        target = match.group(1)
        display = match.group(2) if match.group(2) is not None else target
        return display

    return _WIKILINK_PATTERN.sub(_replace, text)


def detect_author_year(text: str) -> List[str]:
    """Detect plain `(Author Year)`-style citation patterns in CLEAN text.

    Callers should run this against text with wikilinks already stripped
    (see `strip_wikilinks`) so a wikilink's display text is never mistaken
    for an unparsed citation.
    """
    return [match.group(0) for match in _AUTHOR_YEAR_PATTERN.finditer(text)]


def split_sentences(text: str) -> List[str]:
    """Split text into sentences, replicating the pipeline's sentence splitter.

    Mirrors `claim_extractor.nodes.sentence_splitter._sentence_splitter_and_context_creator`
    (lines 59-83): split by paragraph, run NLTK `sent_tokenize` per paragraph,
    then merge fragments shorter than 5 chars into the next sentence. This
    exact replication (including the paragraph-split token) is required so
    sentence indices line up with what the extraction pipeline produces.
    """
    ensure_nltk_resources()

    paragraphs = [p.strip() for p in text.split("\\n") if p.strip()]
    raw_sentences: List[str] = []
    for paragraph in paragraphs:
        raw_sentences.extend(nltk.sent_tokenize(paragraph))

    merged_sentences: List[str] = []
    i = 0
    while i < len(raw_sentences):
        current_sentence = raw_sentences[i].strip()

        while len(current_sentence) < 5 and (i + 1) < len(raw_sentences):
            i += 1
            current_sentence += f" {raw_sentences[i].strip()}"

        if current_sentence:
            merged_sentences.append(current_sentence)
        i += 1

    return merged_sentences


def _locate_sentence(original: str, sentence: str, search_from: int) -> Tuple[int, int]:
    """Find the char span of `sentence` inside `original`, tolerant of whitespace drift.

    `split_sentences()` may strip/re-join whitespace (e.g. merged fragments are
    joined with a single space where the original had a newline), so an exact
    substring search can miss. Build a pattern that treats any run of
    whitespace in `sentence` as `\\s+` and search forward from `search_from`.
    """
    tokens = sentence.split()
    if tokens:
        pattern = re.compile(r"\s+".join(re.escape(tok) for tok in tokens))
        match = pattern.search(original, search_from)
        if match is None:
            match = pattern.search(original)
        if match is not None:
            return match.start(), match.end()

    # Fallback: plain substring search.
    idx = original.find(sentence, search_from)
    if idx == -1:
        idx = original.find(sentence)
    if idx != -1:
        return idx, idx + len(sentence)

    raise ValueError(f"Could not locate sentence in original text: {sentence!r}")


def parse_draft(
    text: str,
    section: Optional[str] = None,
    section_index: Optional[int] = None,
) -> ParsedDraft:
    """Parse a wikilinked draft into sentences with citation metadata.

    Citation scope is sentence-level only: a wikilink or author-year pattern
    is attributed to the sentence it physically appears in, never propagated
    to earlier sentences in the same paragraph.
    """
    wikilinks = parse_wikilinks(text)
    clean_text = strip_wikilinks(text)
    raw_sentences = split_sentences(text)

    sentences: List[ParsedSentence] = []
    cursor = 0
    for index, sentence in enumerate(raw_sentences):
        char_start, char_end = _locate_sentence(text, sentence, cursor)
        cursor = char_end

        cite_set = [
            wl.target
            for wl in wikilinks
            if wl.char_start >= char_start and wl.char_end <= char_end
        ]

        clean_sentence = strip_wikilinks(sentence)
        unparsed_citations = detect_author_year(clean_sentence)

        if cite_set:
            citation_status = CitationStatus.CITED
        elif unparsed_citations:
            citation_status = CitationStatus.UNPARSED_CITATION
        else:
            citation_status = CitationStatus.CITATION_FREE

        sentences.append(
            ParsedSentence(
                sentence_index=index,
                original_text=sentence,
                clean_text=clean_sentence,
                citation_status=citation_status,
                cite_set=cite_set,
                unparsed_citations=unparsed_citations,
                char_start=char_start,
                char_end=char_end,
            )
        )

    return ParsedDraft(
        original_text=text,
        clean_text=clean_text,
        sentences=sentences,
        section=section,
        section_index=section_index,
    )
