"""Pure-text markdown chunking for the fact-checker pipeline.

No docling (or any other PDF) imports here: everything in this module is
deterministic string manipulation, unit-testable fully offline.

A "section" is a plain dict: {"title": str, "text": str}.
"""

from __future__ import annotations

import re
from typing import Dict, List

Section = Dict[str, str]

DEFAULT_MAX_CHARS = 4000
DEFAULT_MIN_CHARS = 200

# Level 1 or 2 markdown heading (### and deeper stay inside their section).
_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")


def split_by_headings(markdown: str) -> List[Section]:
    """Split markdown into sections at level-1/level-2 headings.

    Text before the first heading becomes a section with an empty title.
    Headings inside fenced code blocks are ignored. Whitespace-only input
    yields an empty list.
    """
    if not markdown or not markdown.strip():
        return []

    sections: List[Section] = []
    current_title = ""
    current_lines: List[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text or current_title:
            sections.append({"title": current_title, "text": text})

    for line in markdown.splitlines():
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            current_lines.append(line)
            continue

        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            flush()
            current_title = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    flush()
    return sections


def _split_paragraph_hard(paragraph: str, max_chars: int) -> List[str]:
    """Slice a single oversized paragraph into <= max_chars pieces."""
    return [paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars)]


def enforce_max_size(
    sections: List[Section], max_chars: int = DEFAULT_MAX_CHARS
) -> List[Section]:
    """Split any section whose text exceeds ``max_chars``.

    Splitting happens on paragraph boundaries (blank lines); a lone paragraph
    longer than ``max_chars`` is hard-sliced. Split parts are re-titled
    "<title> (part N)".
    """
    out: List[Section] = []
    for section in sections:
        text = section["text"]
        if len(text) <= max_chars:
            out.append(dict(section))
            continue

        paragraphs: List[str] = []
        for para in re.split(r"\n\s*\n", text):
            para = para.strip("\n")
            if not para:
                continue
            if len(para) > max_chars:
                paragraphs.extend(_split_paragraph_hard(para, max_chars))
            else:
                paragraphs.append(para)

        parts: List[str] = []
        current: List[str] = []
        current_len = 0
        for para in paragraphs:
            extra = len(para) + (2 if current else 0)  # +2 for "\n\n" joiner
            if current and current_len + extra > max_chars:
                parts.append("\n\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += extra
        if current:
            parts.append("\n\n".join(current))

        base_title = section["title"]
        for index, part_text in enumerate(parts, start=1):
            title = f"{base_title} (part {index})" if base_title else f"(part {index})"
            out.append({"title": title, "text": part_text})
    return out


def _merged_text(base: str, tiny: Section) -> str:
    """Text contributed by a tiny section when merged into a neighbor."""
    piece = f"{tiny['title']}\n\n{tiny['text']}" if tiny["title"] else tiny["text"]
    piece = piece.strip()
    if not base:
        return piece
    if not piece:
        return base
    return f"{base}\n\n{piece}"


def merge_tiny_sections(
    sections: List[Section], min_chars: int = DEFAULT_MIN_CHARS
) -> List[Section]:
    """Merge sections shorter than ``min_chars`` into a neighbor.

    Tiny sections merge into the previous section when one exists, otherwise
    into the next one. A document consisting of a single tiny section is
    returned as-is.
    """
    if not sections:
        return []

    merged: List[Section] = []
    pending_leading: List[Section] = []  # tiny sections with no previous neighbor

    for section in sections:
        if len(section["text"]) < min_chars:
            if merged:
                prev = merged[-1]
                merged[-1] = {
                    "title": prev["title"],
                    "text": _merged_text(prev["text"], section),
                }
            else:
                pending_leading.append(section)
            continue

        current = dict(section)
        if pending_leading:
            # Fold leading tiny sections into this first adequate section,
            # keeping the first tiny section's title as the lead title.
            lead = pending_leading[0]
            text = lead["text"]
            for tiny in pending_leading[1:]:
                text = _merged_text(text, tiny)
            body = (
                f"{current['title']}\n\n{current['text']}"
                if current["title"]
                else current["text"]
            )
            current = {
                "title": lead["title"],
                "text": f"{text}\n\n{body}".strip(),
            }
            pending_leading = []
        merged.append(current)

    if pending_leading:
        # Every section was tiny: collapse them into one.
        lead = pending_leading[0]
        text = lead["text"]
        for tiny in pending_leading[1:]:
            text = _merged_text(text, tiny)
        merged.append({"title": lead["title"], "text": text})

    return merged


def chunk_markdown(
    markdown: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> List[Section]:
    """Full chunking pipeline: heading split -> size cap -> tiny merge."""
    sections = split_by_headings(markdown)
    sections = enforce_max_size(sections, max_chars=max_chars)
    sections = merge_tiny_sections(sections, min_chars=min_chars)
    return sections
