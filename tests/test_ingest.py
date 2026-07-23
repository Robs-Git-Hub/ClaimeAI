"""Tests for the ingest package.

The chunking tests are pure-text and run fully offline (no docling, no PDF).
The extraction test is marked slow because docling downloads layout models
on first run.
"""

from pathlib import Path

import pytest

from ingest.chunking import (
    chunk_markdown,
    enforce_max_size,
    merge_tiny_sections,
    split_by_headings,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# split_by_headings
# ---------------------------------------------------------------------------


class TestSplitByHeadings:
    def test_splits_on_level_1_and_2_headings(self):
        md = (
            "# Title\n\nIntro paragraph.\n\n"
            "## Section A\n\nText of A.\n\n"
            "## Section B\n\nText of B.\n"
        )
        sections = split_by_headings(md)
        assert [s["title"] for s in sections] == ["Title", "Section A", "Section B"]
        assert sections[0]["text"] == "Intro paragraph."
        assert sections[1]["text"] == "Text of A."
        assert sections[2]["text"] == "Text of B."

    def test_level_3_headings_stay_inside_section(self):
        md = "## Section A\n\nText.\n\n### Subsection\n\nSub text.\n"
        sections = split_by_headings(md)
        assert len(sections) == 1
        assert sections[0]["title"] == "Section A"
        assert "### Subsection" in sections[0]["text"]
        assert "Sub text." in sections[0]["text"]

    def test_preamble_before_first_heading_is_kept(self):
        md = "Some preamble text before any heading.\n\n# First\n\nBody.\n"
        sections = split_by_headings(md)
        assert len(sections) == 2
        assert sections[0]["title"] == ""
        assert sections[0]["text"] == "Some preamble text before any heading."
        assert sections[1]["title"] == "First"

    def test_no_headings_yields_single_section(self):
        md = "Just a plain paragraph.\n\nAnd another one.\n"
        sections = split_by_headings(md)
        assert len(sections) == 1
        assert sections[0]["title"] == ""
        assert "Just a plain paragraph." in sections[0]["text"]
        assert "And another one." in sections[0]["text"]

    def test_empty_input_yields_no_sections(self):
        assert split_by_headings("") == []
        assert split_by_headings("   \n\n  \n") == []

    def test_heading_with_no_body_is_kept_with_empty_text(self):
        md = "## Empty One\n\n## Full One\n\nBody here.\n"
        sections = split_by_headings(md)
        assert [s["title"] for s in sections] == ["Empty One", "Full One"]
        assert sections[0]["text"] == ""

    def test_hashes_inside_fenced_code_blocks_do_not_split(self):
        md = (
            "## Code Section\n\nBefore code.\n\n"
            "```\n# not a heading\n## also not a heading\n```\n\n"
            "After code.\n"
        )
        sections = split_by_headings(md)
        assert len(sections) == 1
        assert "# not a heading" in sections[0]["text"]
        assert "After code." in sections[0]["text"]


# ---------------------------------------------------------------------------
# enforce_max_size
# ---------------------------------------------------------------------------


class TestEnforceMaxSize:
    def test_small_sections_pass_through_unchanged(self):
        sections = [{"title": "A", "text": "short text"}]
        assert enforce_max_size(sections, max_chars=4000) == sections

    def test_oversized_section_is_split_on_paragraph_boundaries(self):
        paras = [f"Paragraph {i}. " + ("x" * 90) for i in range(10)]
        text = "\n\n".join(paras)  # ~1000+ chars
        sections = [{"title": "Big", "text": text}]
        out = enforce_max_size(sections, max_chars=300)
        assert len(out) > 1
        for part in out:
            assert len(part["text"]) <= 300
        # No paragraph was broken across parts.
        rejoined = [p for part in out for p in part["text"].split("\n\n")]
        assert rejoined == paras

    def test_split_parts_get_numbered_titles(self):
        paras = ["a" * 150, "b" * 150, "c" * 150]
        sections = [{"title": "Long", "text": "\n\n".join(paras)}]
        out = enforce_max_size(sections, max_chars=200)
        assert [p["title"] for p in out] == [
            "Long (part 1)",
            "Long (part 2)",
            "Long (part 3)",
        ]

    def test_single_paragraph_larger_than_max_is_hard_split(self):
        text = "z" * 950
        out = enforce_max_size([{"title": "Huge", "text": text}], max_chars=300)
        assert len(out) == 4
        assert all(len(p["text"]) <= 300 for p in out)
        assert "".join(p["text"] for p in out) == text

    def test_deterministic(self):
        paras = [f"Para {i} " + "y" * 120 for i in range(8)]
        sections = [{"title": "T", "text": "\n\n".join(paras)}]
        assert enforce_max_size(sections, max_chars=400) == enforce_max_size(
            sections, max_chars=400
        )


# ---------------------------------------------------------------------------
# merge_tiny_sections
# ---------------------------------------------------------------------------


class TestMergeTinySections:
    def test_tiny_section_merges_into_previous_neighbor(self):
        sections = [
            {"title": "A", "text": "x" * 500},
            {"title": "Tiny", "text": "tiny body"},
            {"title": "B", "text": "y" * 500},
        ]
        out = merge_tiny_sections(sections, min_chars=200)
        assert len(out) == 2
        assert out[0]["title"] == "A"
        # The tiny section's title and text survive inside the merged section.
        assert "Tiny" in out[0]["text"]
        assert "tiny body" in out[0]["text"]
        assert out[1]["title"] == "B"

    def test_leading_tiny_section_merges_into_next_neighbor(self):
        sections = [
            {"title": "Tiny", "text": "small"},
            {"title": "A", "text": "x" * 500},
        ]
        out = merge_tiny_sections(sections, min_chars=200)
        assert len(out) == 1
        assert out[0]["title"] == "Tiny"
        assert "small" in out[0]["text"]
        assert "x" * 500 in out[0]["text"]

    def test_single_tiny_section_is_kept(self):
        sections = [{"title": "Only", "text": "just this"}]
        out = merge_tiny_sections(sections, min_chars=200)
        assert len(out) == 1
        assert "just this" in out[0]["text"]

    def test_adequate_sections_untouched(self):
        sections = [
            {"title": "A", "text": "x" * 300},
            {"title": "B", "text": "y" * 300},
        ]
        assert merge_tiny_sections(sections, min_chars=200) == sections

    def test_consecutive_tiny_sections_all_get_merged(self):
        sections = [
            {"title": "A", "text": "x" * 500},
            {"title": "T1", "text": "one"},
            {"title": "T2", "text": "two"},
        ]
        out = merge_tiny_sections(sections, min_chars=200)
        assert len(out) == 1
        assert "one" in out[0]["text"]
        assert "two" in out[0]["text"]

    def test_empty_list(self):
        assert merge_tiny_sections([], min_chars=200) == []


# ---------------------------------------------------------------------------
# chunk_markdown (end-to-end over text)
# ---------------------------------------------------------------------------


class TestChunkMarkdown:
    def test_full_pipeline(self):
        big_body = "\n\n".join("Fact paragraph. " + "w" * 180 for _ in range(6))
        md = (
            "# Doc Title\n\nA reasonable intro paragraph with enough text to stand "
            "alone as its own section for the fact checker to process properly. "
            + "filler " * 30
            + "\n\n## Big Section\n\n"
            + big_body
            + "\n\n## Stub\n\nToo small.\n"
        )
        sections = chunk_markdown(md, max_chars=500, min_chars=100)
        assert sections, "expected at least one section"
        for s in sections:
            assert set(s.keys()) == {"title", "text"}
            assert len(s["text"]) <= 500
        # tiny 'Stub' section merged away
        assert all(s["title"] != "Stub" for s in sections)
        assert any("Too small." in s["text"] for s in sections)

    def test_empty_markdown(self):
        assert chunk_markdown("") == []

    def test_defaults_are_applied(self):
        md = "## A\n\n" + "text " * 50
        sections = chunk_markdown(md)
        assert len(sections) == 1


# ---------------------------------------------------------------------------
# PDF extraction (slow: docling downloads models on first run)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_extract_pdf_fixture():
    from ingest.pdf import extract_pdf

    fixture = FIXTURES / "sample.pdf"
    assert fixture.exists(), "run tests/fixtures/make_fixture.py to generate it"
    try:
        markdown = extract_pdf(fixture)
    except Exception as exc:  # pragma: no cover - network-dependent
        msg = str(exc).lower()
        if any(
            k in msg
            for k in ("download", "connect", "http", "network", "timeout", "resolve")
        ):
            pytest.skip(f"docling model download unavailable: {exc}")
        raise
    assert "Solar System Facts" in markdown
    assert "The Inner Planets" in markdown
    assert "The Outer Planets" in markdown
    assert "Mercury" in markdown
    assert "Jupiter" in markdown

    # The extracted markdown should chunk into titled sections.
    sections = chunk_markdown(markdown, min_chars=50)
    assert len(sections) >= 2


# ---------------------------------------------------------------------------
# report.md rendering for scripts/run_from_pdf.py
# ---------------------------------------------------------------------------


class TestRenderReportMd:
    def _fake_results(self):
        report = {
            "answer": "Mercury is the closest planet to the Sun.",
            "claims_verified": 2,
            "verified_claims": [
                {
                    "claim_text": "Mercury is the closest planet to the Sun.",
                    "result": "Supported",
                    "reasoning": "Multiple sources confirm this.",
                    "sources": [{"url": "https://example.com/a", "title": "A"}],
                },
                {
                    "claim_text": "Mercury has two moons.",
                    "result": "Refuted",
                    "reasoning": "Mercury has no moons.",
                    "sources": [],
                },
            ],
            "summary": "1 supported, 1 refuted.",
            "timestamp": "2026-07-22T10:00:00",
        }
        return [
            {
                "title": "The Inner Planets",
                "text": "Mercury is the closest planet to the Sun.",
                "report": report,
            },
            {"title": "Failed Section", "text": "whatever", "error": "boom"},
        ]

    def test_render_report_md(self):
        from scripts.run_from_pdf import render_report_md

        md = render_report_md("sample.pdf", self._fake_results())
        assert "sample.pdf" in md
        assert "The Inner Planets" in md
        assert "1 supported, 1 refuted." in md
        # verdict table rows
        assert "Supported" in md
        assert "Refuted" in md
        assert "Mercury has two moons." in md
        assert "Mercury has no moons." in md
        assert "https://example.com/a" in md
        # failed section is reported, not silently dropped
        assert "Failed Section" in md
        assert "boom" in md

    def test_render_report_md_escapes_pipes_in_table_cells(self):
        from scripts.run_from_pdf import render_report_md

        results = [
            {
                "title": "S",
                "text": "t",
                "report": {
                    "answer": "t",
                    "claims_verified": 1,
                    "verified_claims": [
                        {
                            "claim_text": "a | b",
                            "result": "Supported",
                            "reasoning": "c | d",
                            "sources": [],
                        }
                    ],
                    "summary": "ok",
                    "timestamp": "2026-07-22T10:00:00",
                },
            }
        ]
        md = render_report_md("x.pdf", results)
        assert "a \\| b" in md
        assert "c \\| d" in md
