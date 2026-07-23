"""Run the fact-checker pipeline over a PDF or text file, section by section.

Accepts a PDF (extracted with Docling) or a plain .md/.markdown/.txt file
(read directly, no Docling). Either way the content is chunked into
sections and each section is sent through the `fact_checker` LangGraph
(must be running: `langgraph dev --no-browser`). Results are written to
workspace/output/<file-stem>/:

    results.json  - structured per-section reports
    report.md     - readable per-section verdict tables + summaries

Usage:
    poetry run python scripts/run_from_pdf.py [path/to/file.pdf|.md|.txt]

With no argument, the newest PDF in workspace/inbox/ is used. Supported
extensions: .pdf, .md, .markdown, .txt (case-insensitive).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "workspace" / "inbox"
OUTPUT_DIR = REPO_ROOT / "workspace" / "output"
DEFAULT_URL = "http://127.0.0.1:2024"
ASSISTANT_ID = "fact_checker"

PDF_EXTENSION = ".pdf"
TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
SUPPORTED_EXTENSIONS = {PDF_EXTENSION} | TEXT_EXTENSIONS


# ---------------------------------------------------------------------------
# Input loading (dispatch on file extension; pure/offline for text inputs)
# ---------------------------------------------------------------------------


def load_sections(
    path: Path, max_chars: int, min_chars: int
) -> List[Dict[str, str]]:
    """Load a file and chunk it into fact-checker-ready sections.

    Dispatches on file extension:
        .pdf                     -> Docling extraction, then chunk_markdown
        .md / .markdown / .txt   -> read as UTF-8 text, then chunk_markdown

    Raises:
        ValueError: if the extension is not one of SUPPORTED_EXTENSIONS.
    """
    suffix = path.suffix.lower()
    if suffix == PDF_EXTENSION:
        from ingest import pdf_to_sections

        return pdf_to_sections(path, max_chars=max_chars, min_chars=min_chars)
    if suffix in TEXT_EXTENSIONS:
        from ingest.chunking import chunk_markdown

        text = path.read_text(encoding="utf-8")
        return chunk_markdown(text, max_chars=max_chars, min_chars=min_chars)
    raise ValueError(
        f"Unsupported file type '{suffix or path.name}'. "
        f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


# ---------------------------------------------------------------------------
# Report rendering (pure functions, unit-tested offline)
# ---------------------------------------------------------------------------


def _md_cell(value: Any) -> str:
    """Make a value safe for a markdown table cell."""
    text = str(value).replace("|", "\\|").replace("\n", " ").strip()
    return text


def render_report_md(pdf_name: str, section_results: List[Dict[str, Any]]) -> str:
    """Render per-section fact-check results as readable markdown.

    Each item in ``section_results`` is a dict with keys:
        title, text, and either report (FactCheckReport-shaped dict)
        or error (string).
    """
    lines: List[str] = [
        f"# Fact-check report: {pdf_name}",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Sections checked: {len(section_results)}",
        "",
    ]

    for index, section in enumerate(section_results, start=1):
        title = section.get("title") or f"Section {index}"
        lines.append(f"## {index}. {title}")
        lines.append("")

        error = section.get("error")
        report = section.get("report")
        if error or not report:
            lines.append(f"**Error:** {error or 'no report returned'}")
            lines.append("")
            continue

        summary = report.get("summary", "")
        if summary:
            lines.append(f"**Summary:** {summary}")
            lines.append("")

        claims = report.get("verified_claims") or []
        lines.append(f"Claims verified: {report.get('claims_verified', len(claims))}")
        lines.append("")

        if claims:
            lines.append("| # | Claim | Verdict | Reasoning | Sources |")
            lines.append("|---|-------|---------|-----------|---------|")
            for claim_index, claim in enumerate(claims, start=1):
                sources = claim.get("sources") or []
                source_links = ", ".join(
                    _md_cell(s.get("url", "")) for s in sources if s.get("url")
                )
                lines.append(
                    "| {n} | {claim} | {verdict} | {reasoning} | {sources} |".format(
                        n=claim_index,
                        claim=_md_cell(claim.get("claim_text", "")),
                        verdict=_md_cell(claim.get("result", "")),
                        reasoning=_md_cell(claim.get("reasoning", "")),
                        sources=source_links or "-",
                    )
                )
            lines.append("")
        else:
            lines.append("No claims were extracted from this section.")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Graph invocation
# ---------------------------------------------------------------------------


def _thread_id_for(text: str) -> str:
    return str(uuid.UUID(hex=hashlib.md5(text.encode("UTF-8")).hexdigest()))


async def _check_section(client: Any, section: Dict[str, str]) -> Dict[str, Any]:
    """Run one section through the fact_checker graph and return its result."""
    payload = {"answer": section["text"]}
    thread_id = _thread_id_for(section["text"])

    try:
        await client.threads.delete(thread_id)
    except Exception:
        pass

    await client.threads.create(thread_id=thread_id)
    final_state = await client.runs.wait(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        input=payload,
    )

    result: Dict[str, Any] = {"title": section["title"], "text": section["text"]}
    report = None
    if isinstance(final_state, dict):
        report = final_state.get("final_report")
    if report:
        result["report"] = report
    else:
        result["error"] = "run finished without a final_report"
    return result


def _newest_inbox_pdf() -> Path:
    pdfs = sorted(
        INBOX_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not pdfs:
        sys.exit(
            f"No PDF given and no PDFs found in {INBOX_DIR}. "
            "Drop a PDF into workspace/inbox/ or pass a path."
        )
    return pdfs[0]


async def run(pdf_path: Path, url: str, max_chars: int, min_chars: int) -> Path:
    from langgraph_sdk import get_client

    if pdf_path.suffix.lower() == PDF_EXTENSION:
        print(f"Extracting {pdf_path} (first docling run may download models)...")
    else:
        print(f"Reading {pdf_path}...")
    try:
        sections = load_sections(pdf_path, max_chars=max_chars, min_chars=min_chars)
    except ValueError as exc:
        sys.exit(str(exc))
    if not sections:
        sys.exit(f"No text sections could be extracted from {pdf_path}.")
    print(f"Extracted {len(sections)} section(s).")

    client = get_client(url=url)

    section_results: List[Dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        label = section["title"] or f"Section {index}"
        print(f"[{index}/{len(sections)}] Fact-checking: {label}")
        try:
            section_results.append(await _check_section(client, section))
        except (ConnectionError, OSError) as exc:
            _die_server_not_running(url, exc)
        except Exception as exc:
            if _looks_like_connection_error(exc):
                _die_server_not_running(url, exc)
            print(f"  Section failed: {exc}")
            section_results.append(
                {"title": section["title"], "text": section["text"], "error": str(exc)}
            )

    out_dir = OUTPUT_DIR / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "pdf": str(pdf_path),
        "generated": datetime.now().isoformat(timespec="seconds"),
        "sections": section_results,
    }
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(
        render_report_md(pdf_path.name, section_results), encoding="utf-8"
    )
    print(f"Wrote {out_dir / 'results.json'}")
    print(f"Wrote {out_dir / 'report.md'}")
    return out_dir


def _looks_like_connection_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(
        needle in text
        for needle in ("connect", "refused", "unreachable", "actively refused")
    )


def _die_server_not_running(url: str, exc: Exception) -> None:
    sys.exit(
        f"Could not reach the LangGraph server at {url} ({exc}).\n"
        "Start it first with:\n\n    langgraph dev --no-browser\n"
    )


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fact-check a PDF or text/markdown file section by section via "
            "the fact_checker graph."
        )
    )
    parser.add_argument(
        "pdf",
        nargs="?",
        type=Path,
        default=None,
        help=(
            "Path to a .pdf, .md, .markdown, or .txt file "
            "(default: newest PDF in workspace/inbox/)"
        ),
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"LangGraph server URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum characters per section (default: 4000)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=200,
        help="Sections shorter than this merge into a neighbor (default: 200)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(argv)
    pdf_path = args.pdf if args.pdf is not None else _newest_inbox_pdf()
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        sys.exit(f"File not found: {pdf_path}")
    if pdf_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        sys.exit(
            f"Unsupported file type '{pdf_path.suffix or pdf_path.name}'. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    asyncio.run(run(pdf_path, args.url, args.max_chars, args.min_chars))


if __name__ == "__main__":
    main()
