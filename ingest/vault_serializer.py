"""Obsidian vault serializer (TG 02.3).

Parses an Obsidian vault (frontmatter + markdown body notes) into a JSON
evidence corpus suitable for LLM-based claim matching.

Read-only against the vault: this module never writes, moves, or modifies
vault files.

Vault schema notes (discovered from the real vault, not assumed):
    - Frontmatter uses a ``type`` field (not ``note_type``).
    - The note's FILE PREFIX does not always match its frontmatter ``type``:
      SOURCE- notes use subtype values (academic-paper, dataset,
      policy-paper, web-page, source-dataset, data-source, ...), and
      QUOTE- notes use "quotation", not "quote".
    - ``argument_pyramid`` is a YAML list field, e.g. ``[pyramid-name]``.
    - Body sections are split on level-2 (``##``) markdown headings.

See:
    C:/Users/.../ukraine-vote-analysis/vault-main/_index/property-enums.md
    C:/Users/.../ukraine-vote-analysis/vault-main/v-research/DESIGN-argument-pyramid-note-type-architecture.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Evidence-bearing note types, discovered from the real vault (not the file
# prefix — see module docstring). Callers may pass a custom set instead;
# load_vault() applies NO type filter when evidence_types is left as None.
DEFAULT_EVIDENCE_TYPES: Set[str] = {
    # SOURCE- subtype values (property-enums.md documents 8; the live vault
    # also has "source-dataset" and "data-source" from schema drift).
    "web-page",
    "academic-paper",
    "policy-paper",
    "grant-programme",
    "org-website",
    "scholar-profile",
    "book-note",
    "dataset",
    "source-dataset",
    "data-source",
    # Evidence-chain types (property-enums.md "Evidence Chain" list).
    "quotation",
    "paraphrase",
    "observation",
    "claim",
    "thesis",
    "hypothesis",
    "interpretation",
    "experiment",
    "result",
}

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class VaultNote(BaseModel):
    """A single parsed Obsidian vault note."""

    name: str = Field(description="Filename without .md")
    note_type: str = Field(description="Value of the frontmatter `type` field, or 'unknown'")
    frontmatter: Dict[str, Any] = Field(default_factory=dict, description="All frontmatter fields as-is")
    body_sections: Dict[str, str] = Field(default_factory=dict, description="Heading -> section text")
    wikilinks: List[str] = Field(default_factory=list, description="Outgoing [[target]] names from body")
    file_path: str = Field(description="Path relative to the vault root")


class SerializedVault(BaseModel):
    """A vault (or filtered subset) serialized for LLM consumption."""

    notes: List[Dict[str, Any]] = Field(description="Serialized note dicts")
    note_count: int = Field(description="Number of notes")
    token_estimate: int = Field(description="Approximate token count (chars / 4)")
    warnings: List[str] = Field(default_factory=list, description="e.g. budget-exceeded warnings")
    argument_pyramid: Optional[str] = Field(default=None, description="Filter applied, if any")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split ``text`` into (raw_frontmatter_yaml, body). Empty string if none found."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group(1), text[match.end():]


def _split_body_sections(body: str) -> Dict[str, str]:
    """Split ``body`` into heading -> content, splitting on level-2 (##) headings.

    Text before the first ``##`` heading (if any, and non-empty) is stored
    under the empty-string key, matching the convention used by
    ``ingest.chunking.split_by_headings``.
    """
    sections: Dict[str, str] = {}

    matches = list(_HEADING_RE.finditer(body))
    if not matches:
        stripped = body.strip()
        if stripped:
            sections[""] = stripped
        return sections

    preamble = body[: matches[0].start()].strip()
    if preamble:
        sections[""] = preamble

    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        sections[title] = content

    return sections


def _extract_wikilinks(body: str) -> List[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(body)]


def parse_vault_note(path: Path) -> VaultNote:
    """Parse a single .md vault note into a VaultNote.

    Gracefully degrades: missing or malformed frontmatter yields an empty
    frontmatter dict and note_type "unknown" rather than raising.
    """
    text = path.read_text(encoding="utf-8")
    raw_frontmatter, body = _split_frontmatter(text)

    frontmatter: Dict[str, Any] = {}
    if raw_frontmatter:
        try:
            parsed = yaml.safe_load(raw_frontmatter)
            if isinstance(parsed, dict):
                frontmatter = parsed
        except yaml.YAMLError:
            frontmatter = {}

    note_type = frontmatter.get("type")
    if not isinstance(note_type, str) or not note_type:
        note_type = "unknown"

    body_sections = _split_body_sections(body)
    wikilinks = _extract_wikilinks(body)

    return VaultNote(
        name=path.stem,
        note_type=note_type,
        frontmatter=frontmatter,
        body_sections=body_sections,
        wikilinks=wikilinks,
        file_path=path.name,
    )


def load_vault(
    vault_path: Path,
    research_dir: str = "v-research",
    argument_pyramid: Optional[str] = None,
    evidence_types: Optional[Set[str]] = None,
) -> List[VaultNote]:
    """Walk ``vault_path / research_dir`` and parse every .md note.

    With no filters, every parseable note is returned. Pass
    ``evidence_types=DEFAULT_EVIDENCE_TYPES`` (or a custom set) to restrict
    to evidence-bearing note types; pass ``argument_pyramid`` to restrict to
    notes tagged into a named argument-pyramid exercise.
    """
    research_path = Path(vault_path) / research_dir
    notes: List[VaultNote] = []

    for md_path in sorted(research_path.rglob("*.md")):
        note = parse_vault_note(md_path)
        note.file_path = str(md_path.relative_to(vault_path))
        notes.append(note)

    if argument_pyramid is not None:
        filtered = []
        for note in notes:
            value = note.frontmatter.get("argument_pyramid")
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            if argument_pyramid in values:
                filtered.append(note)
        notes = filtered

    if evidence_types is not None:
        notes = [note for note in notes if note.note_type in evidence_types]

    return notes


def serialize_vault(
    notes: List[VaultNote],
    token_budget: Optional[int] = None,
    argument_pyramid: Optional[str] = None,
) -> SerializedVault:
    """Serialize parsed notes into an LLM-consumable JSON-friendly corpus."""
    serialized_notes: List[Dict[str, Any]] = []
    for note in notes:
        frontmatter = {key: val for key, val in note.frontmatter.items() if key != "type"}
        serialized_notes.append(
            {
                "name": note.name,
                "type": note.note_type,
                "frontmatter": frontmatter,
                "sections": note.body_sections,
                "wikilinks": note.wikilinks,
            }
        )

    # Frontmatter `date:` fields parse as datetime.date via YAML; stringify
    # anything json.dumps can't natively handle (dates, etc.).
    char_count = len(json.dumps(serialized_notes, default=str))
    token_estimate = char_count // 4

    warnings: List[str] = []
    if token_budget is not None and token_estimate > token_budget:
        warnings.append(
            f"Token estimate {token_estimate} exceeds budget {token_budget}"
        )

    return SerializedVault(
        notes=serialized_notes,
        note_count=len(serialized_notes),
        token_estimate=token_estimate,
        warnings=warnings,
        argument_pyramid=argument_pyramid,
    )
