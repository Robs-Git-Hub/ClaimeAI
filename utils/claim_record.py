"""Multi-attribute claim record (TG 02.1.2).

`ClaimRecord` is the data contract for Phases 02-05. It wraps the existing
Phase 01 `Verdict` model (from `claim_verifier.schemas`) rather than
duplicating its fields, and adds citation, vault-verification, and
Phase 03 triage attributes.

See docs/playbook/claim-record-design.md for the full design contract.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from claim_verifier.schemas import Verdict


class CitationStatus(str, Enum):
    """Whether a claim has a parseable wikilink citation."""

    CITED = "cited"
    CITATION_FREE = "citation_free"
    UNPARSED_CITATION = "unparsed_citation"


class VaultVerdict(str, Enum):
    """Route-specific verdicts for vault-based verification.

    Separate from `VerificationResult` (Supported/Refuted), which is
    web-route-specific.
    """

    VAULT_SUPPORTED = "vault_supported"
    VAULT_CONTRADICTED = "vault_contradicted"
    NOT_SUPPORTED = "not_supported"
    NOTE_NOT_IN_VAULT = "note_not_in_vault"
    INSUFFICIENT_VAULT_CONTENT = "insufficient_vault_content"
    NO_VAULT_MATCH = "no_vault_match"


class SuggestedAction(str, Enum):
    """What the author should do about a claim."""

    NONE = "none"
    FIX_CITATION = "fix_citation"
    ADD_CITATION = "add_citation"
    ADD_VAULT_NOTE = "add_vault_note"
    REVISE_CLAIM = "revise_claim"
    UNRESOLVED = "unresolved"


class DraftPosition(BaseModel):
    """Where a claim appears in the draft.

    `sentence_index` is available from extraction (mapped from
    `original_index`); section and character offsets are populated by
    TG 02.2 draft ingestion.
    """

    sentence_index: int = Field(
        description="Index of the sentence in the source draft (from extraction)"
    )
    section: Optional[str] = Field(
        default=None, description="Section heading the claim appears under"
    )
    section_index: Optional[int] = Field(
        default=None, description="0-based section number"
    )
    char_start: Optional[int] = Field(
        default=None, description="Character offset of the claim start in the draft"
    )
    char_end: Optional[int] = Field(
        default=None, description="Character offset of the claim end in the draft"
    )


class RouteVerdict(BaseModel):
    """A verdict from a specific verification route, with provenance."""

    route: str = Field(description='e.g. "web", "vault_aligned", "vault_matched"')
    verdict: str = Field(
        description="Route-specific verdict value (from VaultVerdict or VerificationResult)"
    )
    reasoning: Optional[str] = Field(default=None, description="Explanation")
    provenance: Optional[str] = Field(
        default=None, description="Note name, quote text, or URL"
    )
    provenance_type: Optional[str] = Field(
        default=None, description='"vault_note", "quote_note", or "web_url"'
    )


class ClaimRecord(BaseModel):
    """Multi-attribute claim record — the data contract for Phases 02-05.

    Wraps the existing Phase 01 `Verdict` rather than replacing it. Phase 03
    fields (`triage_class`, `citation_expectation`, `importance`) default to
    None so later phases don't require schema migrations.
    """

    web_verdict: Optional[Verdict] = Field(
        default=None, description="Existing Phase 01 web verification result"
    )
    citation_status: CitationStatus = Field(
        description="Whether the claim has a parseable citation"
    )
    cite_set: List[str] = Field(
        default_factory=list,
        description="Vault note names from wikilink citations (any type)",
    )
    position: Optional[DraftPosition] = Field(
        default=None, description="Location of the claim in the draft"
    )
    vault_verdicts: List[RouteVerdict] = Field(
        default_factory=list, description="Per-route vault verification results"
    )
    suggested_action: Optional[SuggestedAction] = Field(
        default=None, description="What the author should do"
    )
    claim_strength: Optional[int] = Field(
        default=None, description="Copied from matched vault CLAIM note (1-5)"
    )
    evidence_quality: Optional[int] = Field(
        default=None, description="Copied from matched vault CLAIM note (1-5)"
    )
    triage_class: Optional[str] = Field(
        default=None, description="Phase 03: triviality / importance classification"
    )
    citation_expectation: Optional[str] = Field(
        default=None, description="Phase 03: whether academic citation is expected"
    )
    importance: Optional[int] = Field(
        default=None, description="Phase 03: importance score (1-5)"
    )
