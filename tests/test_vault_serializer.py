"""Tests for the Obsidian vault serializer (TG 02.3).

Parses vault notes (YAML frontmatter + markdown body) into a JSON-friendly
evidence corpus for LLM-based claim matching. NARROW tests run fully offline
against fixture notes in ``tests/fixtures/vault/v-research/``. The single
``@pytest.mark.slow`` test at the end validates against the real Obsidian
vault used for the Ukraine UNGA voting research project.

Fixture set (6 notes, in tests/fixtures/vault/v-research/):
    SOURCE-fixture-academic-paper.md   type: academic-paper (evidence)
    QUOTE-fixture-verbatim-example.md  type: quotation (evidence, pyramid-tagged)
    CLAIM-fixture-example-claim.md     type: claim (evidence, pyramid-tagged, extra field)
    MOC-fixture-non-evidence.md        type: moc (non-evidence, for filter tests)
    BAD-missing-frontmatter.md         no frontmatter at all
    BAD-malformed-yaml.md              unterminated YAML list (parse failure)

Real vault type values differ from the FILE PREFIX: SOURCE- notes use
subtype values (academic-paper, dataset, policy-paper, web-page, ...), not
literal "source"; QUOTE- notes use "quotation", not "quote". Confirmed by
reading tests/fixtures/vault source notes and the property-enums.md registry
at C:/Users/rj_co/OneDrive/Documents/GitHub/Robert-Repos/ukraine-vote-analysis/vault-main/_index/property-enums.md
"""

import json
from pathlib import Path

import pytest

from ingest.vault_serializer import (
    DEFAULT_EVIDENCE_TYPES,
    SerializedVault,
    VaultNote,
    load_vault,
    parse_vault_note,
    serialize_vault,
)

FIXTURES = Path(__file__).parent / "fixtures" / "vault"
LIVE_VAULT = Path(
    "C:/Users/rj_co/OneDrive/Documents/GitHub/Robert-Repos/ukraine-vote-analysis/vault-main"
)


def fixture_path(name: str) -> Path:
    return FIXTURES / "v-research" / name


# ---------------------------------------------------------------------------
# parse_vault_note
# ---------------------------------------------------------------------------


class TestParseVaultNote:
    def test_parse_vault_note_source(self):
        note = parse_vault_note(fixture_path("SOURCE-fixture-academic-paper.md"))

        assert note.name == "SOURCE-fixture-academic-paper"
        assert note.note_type == "academic-paper"
        assert note.frontmatter["title"] == "Fixture — Example Academic Paper"
        assert note.frontmatter["source_url"] == "https://example.org/paper"
        assert note.frontmatter["access"] == "free"
        assert "Description" in note.body_sections
        assert "fixture source note" in note.body_sections["Description"].lower()
        assert "Citation" in note.body_sections
        assert "See also" in note.body_sections

    def test_parse_vault_note_quote(self):
        note = parse_vault_note(fixture_path("QUOTE-fixture-verbatim-example.md"))

        assert note.note_type == "quotation"
        assert note.frontmatter["location"] == "Conclusion, p.7"
        assert note.frontmatter["source"].startswith("Example, A. (2026)")
        assert "Verbatim text" in note.body_sections
        assert "fixture verbatim quote" in note.body_sections["Verbatim text"]

    def test_parse_vault_note_claim(self):
        note = parse_vault_note(fixture_path("CLAIM-fixture-example-claim.md"))

        assert note.note_type == "claim"
        assert note.frontmatter["claim_strength"] == 4
        assert note.frontmatter["evidence_quality"] == 3
        assert "Claim" in note.body_sections
        assert "Warrant" in note.body_sections

    def test_parse_vault_note_missing_frontmatter(self):
        note = parse_vault_note(fixture_path("BAD-missing-frontmatter.md"))

        assert note.note_type == "unknown"
        assert note.frontmatter == {}
        # Body content should still be present/parseable.
        assert any("no YAML frontmatter" in text for text in note.body_sections.values())

    def test_parse_vault_note_malformed_yaml(self):
        note = parse_vault_note(fixture_path("BAD-malformed-yaml.md"))

        assert note.note_type == "unknown"
        assert note.frontmatter == {}

    def test_parse_vault_note_extra_fields(self):
        note = parse_vault_note(fixture_path("CLAIM-fixture-example-claim.md"))

        assert note.frontmatter["custom_field"] == "unexpected-value"
        assert note.frontmatter["subtype"] == "major"

    def test_parse_vault_note_wikilinks_extracted(self):
        note = parse_vault_note(fixture_path("CLAIM-fixture-example-claim.md"))

        assert "QUOTE-fixture-verbatim-example" in note.wikilinks
        assert "OBS-fixture-not-included" in note.wikilinks
        assert "THESIS-fixture-not-included" in note.wikilinks

    def test_parse_vault_note_wikilink_with_pipe(self):
        note = parse_vault_note(fixture_path("SOURCE-fixture-academic-paper.md"))

        # [[QUOTE-fixture-verbatim-example|Fixture Quote]] -> only the target
        assert "QUOTE-fixture-verbatim-example" in note.wikilinks
        assert "Fixture Quote" not in note.wikilinks
        assert "MOC-fixture-datasets" in note.wikilinks

    def test_body_section_splitting(self):
        note = parse_vault_note(fixture_path("SOURCE-fixture-academic-paper.md"))

        assert set(note.body_sections) == {"Description", "Citation", "See also"}
        assert note.body_sections["Citation"].startswith("Example, A. (2026)")

    def test_file_path_is_relative(self):
        note = parse_vault_note(fixture_path("SOURCE-fixture-academic-paper.md"))

        assert "SOURCE-fixture-academic-paper.md" in note.file_path
        assert not Path(note.file_path).is_absolute()


# ---------------------------------------------------------------------------
# load_vault
# ---------------------------------------------------------------------------


class TestLoadVault:
    def test_load_vault_all_notes(self):
        notes = load_vault(FIXTURES)

        names = {n.name for n in notes}
        assert names == {
            "SOURCE-fixture-academic-paper",
            "QUOTE-fixture-verbatim-example",
            "CLAIM-fixture-example-claim",
            "MOC-fixture-non-evidence",
            "BAD-missing-frontmatter",
            "BAD-malformed-yaml",
        }

    def test_load_vault_no_filters(self):
        notes = load_vault(FIXTURES, argument_pyramid=None, evidence_types=None)

        assert len(notes) == 6

    def test_load_vault_filter_by_type(self):
        notes = load_vault(FIXTURES, evidence_types=DEFAULT_EVIDENCE_TYPES)

        names = {n.name for n in notes}
        assert "MOC-fixture-non-evidence" not in names
        assert "BAD-missing-frontmatter" not in names
        assert "BAD-malformed-yaml" not in names
        assert "SOURCE-fixture-academic-paper" in names
        assert "QUOTE-fixture-verbatim-example" in names
        assert "CLAIM-fixture-example-claim" in names

    def test_load_vault_filter_by_custom_types(self):
        notes = load_vault(FIXTURES, evidence_types={"claim"})

        names = {n.name for n in notes}
        assert names == {"CLAIM-fixture-example-claim"}

    def test_load_vault_filter_by_argument_pyramid(self):
        notes = load_vault(FIXTURES, argument_pyramid="test-pyramid-alpha")

        names = {n.name for n in notes}
        assert names == {"QUOTE-fixture-verbatim-example", "CLAIM-fixture-example-claim"}

    def test_load_vault_filter_by_argument_pyramid_no_match(self):
        notes = load_vault(FIXTURES, argument_pyramid="nonexistent-pyramid")

        assert notes == []


# ---------------------------------------------------------------------------
# serialize_vault
# ---------------------------------------------------------------------------


class TestSerializeVault:
    def _sample_notes(self):
        return [
            parse_vault_note(fixture_path("SOURCE-fixture-academic-paper.md")),
            parse_vault_note(fixture_path("QUOTE-fixture-verbatim-example.md")),
        ]

    def test_serialize_vault_output_format(self):
        result = serialize_vault(self._sample_notes())

        assert isinstance(result, SerializedVault)
        assert result.note_count == 2
        for note_dict in result.notes:
            assert set(note_dict) == {"name", "type", "frontmatter", "sections", "wikilinks"}
            assert "type" not in note_dict["frontmatter"]

    def test_serialize_vault_token_estimate(self):
        notes = self._sample_notes()
        result = serialize_vault(notes)

        expected_chars = len(json.dumps(result.notes, default=str))
        assert result.token_estimate == pytest.approx(expected_chars / 4, rel=0.05)

    def test_serialize_vault_budget_warning(self):
        result = serialize_vault(self._sample_notes(), token_budget=10)

        assert any("exceeds budget" in w for w in result.warnings)

    def test_serialize_vault_no_warning_under_budget(self):
        result = serialize_vault(self._sample_notes(), token_budget=1_000_000)

        assert result.warnings == []

    def test_serialize_vault_no_budget(self):
        result = serialize_vault(self._sample_notes(), token_budget=None)

        assert result.warnings == []

    def test_serialize_vault_empty_notes(self):
        result = serialize_vault([])

        assert result.note_count == 0
        assert result.notes == []
        assert result.warnings == []


# ---------------------------------------------------------------------------
# Live vault validation (offline dev machine only)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestLiveVault:
    def test_live_vault_all_notes_parse(self):
        if not LIVE_VAULT.exists():
            pytest.skip(f"Live vault not present at {LIVE_VAULT}")

        notes = load_vault(LIVE_VAULT)

        assert len(notes) == pytest.approx(448, abs=50)

        type_counts = {}
        for note in notes:
            type_counts[note.note_type] = type_counts.get(note.note_type, 0) + 1

        # SOURCE- notes use subtype values, not a literal "source" type.
        source_types = {
            "web-page", "academic-paper", "policy-paper", "grant-programme",
            "org-website", "scholar-profile", "book-note", "dataset",
            "source-dataset", "data-source",
        }
        source_count = sum(type_counts.get(t, 0) for t in source_types)
        quote_count = type_counts.get("quotation", 0)
        claim_count = type_counts.get("claim", 0)
        hyp_count = sum(1 for note in notes if note.name.startswith("HYP-"))

        assert source_count >= 100
        assert quote_count >= 30
        assert claim_count >= 15
        assert hyp_count >= 50

    def test_live_vault_argument_pyramid_filter(self):
        if not LIVE_VAULT.exists():
            pytest.skip(f"Live vault not present at {LIVE_VAULT}")

        notes = load_vault(
            LIVE_VAULT, argument_pyramid="un-ukraine-russia-war-votes-working-paper"
        )

        assert 100 <= len(notes) <= 130
