"""Run configuration models (TG 02.1.3).

Declares what evidence sources exist for a fact-checking run. Code should
consult the ``ResourceManifest`` rather than assuming resources exist —
absence of a resource (e.g. no vault) is a no-op, not an error.

See docs/playbook/claim-record-design.md for the design contract.
"""

from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class RunProfile(str, Enum):
    """Which verification behavior a run should use.

    - ``light``: Phase 01 behavior -- web verification only, no vault.
      For blogs and quick checks.
    - ``heavy``: Full attribute set -- vault verification + web. For
      academic drafts with a vault.
    """

    LIGHT = "light"
    HEAVY = "heavy"


class ResourceManifest(BaseModel):
    """Declares what evidence sources exist for a run.

    Absence of a resource is a no-op, not an error: a manifest without
    ``vault_path`` produces a vault-less run plan (no vault sections in
    the report, rather than empty ones).
    """

    draft_path: Path = Field(description="Path to the draft being checked")
    vault_path: Optional[Path] = Field(
        default=None, description="Path to Obsidian vault root"
    )
    argument_pyramid: Optional[str] = Field(
        default=None, description="Vault filter (frontmatter value)"
    )
    corpus_ids: Optional[List[str]] = Field(
        default=None, description="Phase 03: doc-rag-backend document IDs"
    )
    web_enabled: bool = Field(
        default=True, description="Whether web search is available"
    )

    @property
    def has_vault(self) -> bool:
        """Whether this manifest declares a vault to verify against."""
        return self.vault_path is not None

    @property
    def available_routes(self) -> List[str]:
        """Verification routes available given this manifest's resources."""
        routes: List[str] = []
        if self.web_enabled:
            routes.append("web")
        if self.vault_path is not None:
            routes.extend(["vault_aligned", "vault_matched"])
        return routes
