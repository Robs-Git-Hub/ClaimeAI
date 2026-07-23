"""PDF ingestion for the fact-checker pipeline.

Public API:
    extract_pdf(path)      -> markdown text (Docling; slow on first run)
    chunk_markdown(text)   -> list of {"title", "text"} sections (pure text)
    pdf_to_sections(path)  -> convenience: extract then chunk
"""

from pathlib import Path
from typing import List, Union

from ingest.chunking import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    Section,
    chunk_markdown,
)
from ingest.pdf import extract_pdf

__all__ = ["extract_pdf", "chunk_markdown", "pdf_to_sections"]


def pdf_to_sections(
    path: Union[str, Path],
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> List[Section]:
    """Extract a PDF and chunk it into fact-checker-ready sections."""
    markdown = extract_pdf(path)
    return chunk_markdown(markdown, max_chars=max_chars, min_chars=min_chars)
