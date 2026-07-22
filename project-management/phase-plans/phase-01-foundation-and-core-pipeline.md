# Phase 01: Foundation & Core Pipeline

**Status:** IN PROGRESS
**Started:** 2026-07-22
**Goal:** Transform the ClaimeAI fork from a full-stack monorepo into a lean, CLI-driven fact-checking tool with PDF ingestion and a Claude Code skill.

---

## Context

ClaimeAI was forked from BharathxD/ClaimeAI — a LangGraph-based fact-checking system with a Next.js frontend, Chrome extension, and Python agent backend. The agent backend is the only valuable part for our use case: extracting factual claims from text and verifying them against web evidence.

The fork needs to be stripped to the agent only, given PDF input capability (reusing the Docling process from doc-rag-backend), and wrapped in a `/claimify` skill for Claude Code orchestration. OpenRouter support is added alongside the existing OpenAI integration to provide model flexibility.

## Dependencies

- **doc-rag-backend** (Mac only) — Docling PDF extraction process. TG 01.4 requires investigating this on Mac to understand the sentence/span output format.
- **OpenRouter API key** — needed for TG 01.3 testing.
- **Exa AI API key** — needed for web search in the verification pipeline.
- **Redis** — needed for LangGraph. Run via Docker: `docker run -p 6379:6379 redis/redis-stack-server:6.2.6-v17`

## Task Groups

### TG 01.1: PM Structure ✓

Set up CLAUDE.md, HANDOVER.md, project-management directory, REPO note in control hub. This is done.

### TG 01.2: Strip to Agent-Only

Remove the Next.js web app (`apps/web/`), Chrome extension (`apps/extension/`), and Turborepo orchestration. Flatten `apps/agent/*` to the repo root. Remove ~2GB of unused ML dependencies (torch, transformers, sentence-transformers, etc.) that are declared but never imported.

**Risk:** Path references in `langgraph.json` and internal imports may break after flattening. Run `langgraph dev` and the test scripts after every structural change.

### TG 01.3: OpenRouter Integration

Add OpenRouter as a second LLM provider alongside OpenAI. OpenRouter uses the OpenAI-compatible API format, so `langchain-openai` works with a different base URL and API key. The selection is controlled by a `LLM_PROVIDER` env var.

Model mapping (OpenAI → OpenRouter/Claude equivalents):

| Current (OpenAI)  | Role                      | OpenRouter equivalent    |
| ------------------ | ------------------------- | ------------------------ |
| gpt-4o-mini        | Claim extraction (all)    | claude-haiku-4-5         |
| gpt-4.1-mini       | Query gen, search decision| claude-sonnet-4           |
| gpt-4.1            | Evidence evaluation       | claude-opus-4             |

**Important:** The voting mechanism (3 completions, 2/3 consensus) and evidence evaluation must use capable models. Do not map the evidence evaluation call to anything below Opus-tier.

### TG 01.4: PDF Ingest

Add a thin `ingest/` module that reads PDFs and outputs structured text. Reuse the Docling process from doc-rag-backend where possible — it already handles PDF parsing with sentence-level output.

**Investigation needed (on Mac):** Check doc-rag-backend for a standalone function that takes a PDF and returns sentences with metadata. If it exists, extract or import it. If not, use `pymupdf` or `docling` directly.

The ingest module feeds sections to the existing fact-checker graph. Long papers are chunked by section and processed independently.

### TG 01.5: Claimify Skill

Create `.claude/skills/claimify.md` that orchestrates the full pipeline from Claude Code:

1. Start LangGraph dev server (if not running)
2. Accept a file path argument (PDF or text)
3. Extract text via ingest module
4. Run fact-checker per section
5. Write results to `workspace/output/`

### TG 01.6: Quality & Wrap

End-to-end test on a real paper. Update handover.

## Success Criteria

- `langgraph dev` starts from the flattened repo root
- A PDF dropped in `workspace/inbox/` can be fact-checked via `/claimify`
- Both OpenAI and OpenRouter providers work
- Results are written as structured JSON + readable Markdown report

---

## Phase 02 Preview: Argument Chain Verification

**Not started.** Future phase that integrates ClaimeAI with Obsidian vaults containing argument pyramids (from the article-writer-research-of-agents pipeline). Instead of verifying claims against the web, this workflow checks for present and missing links in argument chains and outputs a gap report. An advanced version lets the user indicate what to do about each gap.

## Lessons

(To be populated during execution.)
