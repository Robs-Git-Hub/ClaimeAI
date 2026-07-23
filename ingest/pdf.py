"""PDF extraction via Docling.

All docling surface area lives in this module. Docling is imported lazily so
that importing the ingest package (e.g. for offline chunking tests or CLI
--help) stays fast and works without triggering model loading.

Note: on first use docling downloads its layout models (several hundred MB),
which can take minutes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


def extract_pdf(path: Union[str, Path]) -> str:
    """Convert a PDF to markdown text using Docling.

    Args:
        path: Path to the PDF file.

    Returns:
        The document content as markdown (headings preserved as #/## etc.).

    Raises:
        FileNotFoundError: if the PDF does not exist.
    """
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    return result.document.export_to_markdown()
