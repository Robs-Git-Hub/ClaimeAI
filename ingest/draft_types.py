"""Shared data types for draft parsing and citation binding (TG 02.2).

Both ``ingest.draft_parser`` and ``ingest.citation_binder`` import from
here so they can be developed (and tested) independently.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from utils.claim_record import CitationStatus


class WikilinkCitation(BaseModel):
    """A single wikilink citation found in the draft text."""

    target: str = Field(description="Wikilink target, e.g. 'SOURCE-de-carvalho-2025'")
    display: str = Field(description="Display text, e.g. 'de Carvalho (2025)'")
    char_start: int = Field(description="Start position in original text")
    char_end: int = Field(description="End position in original text (exclusive)")


class ParsedSentence(BaseModel):
    """A sentence from the draft with its citation metadata."""

    sentence_index: int = Field(description="Index in the sentence list (matches pipeline original_index)")
    original_text: str = Field(description="Sentence text with wikilinks intact")
    clean_text: str = Field(description="Sentence text with wikilinks replaced by display text")
    citation_status: CitationStatus = Field(description="Citation classification for this sentence")
    cite_set: List[str] = Field(default_factory=list, description="SOURCE note names from wikilinks")
    unparsed_citations: List[str] = Field(default_factory=list, description="Author-year patterns detected but not bound")
    char_start: int = Field(description="Start position in original draft text")
    char_end: int = Field(description="End position in original draft text (exclusive)")


class ParsedDraft(BaseModel):
    """Result of parsing a draft: sentences with citation metadata."""

    original_text: str = Field(description="Full draft text with wikilinks")
    clean_text: str = Field(description="Full draft text with wikilinks stripped to display text")
    sentences: List[ParsedSentence] = Field(description="Per-sentence citation data")
    section: Optional[str] = Field(default=None, description="Section heading (if processing per-section)")
    section_index: Optional[int] = Field(default=None, description="0-based section number")
