# Session Handover

**Last Updated:** 2026-07-22
**Current Status:** Phase 01 IN PROGRESS (TG 01.1 complete)

---

## Start Here

**Outgoing session completed:** Forked ClaimeAI from BharathxD, cloned locally, configured upstream with push protection. Explored the full repo structure. Created PM structure (CLAUDE.md, HANDOVER.md, TASKS.md, phase plan). Created REPO note in control hub. Created assessment artifact. Saved websearch-and-costs doc.

**Incoming session should:**

1. **Execute TG 01.2 — Strip to Agent-Only.** Move `apps/agent/*` to root, remove web/extension/turborepo, remove unused ML deps. Verify `langgraph dev` starts after flattening.
2. **Execute TG 01.3 — OpenRouter Integration.** Add OpenRouter as alternative LLM provider. Needs OpenRouter API key.
3. **Execute TG 01.4 — PDF Ingest.** Investigate doc-rag-backend's Docling process (on Mac — not cloned on Windows). Create ingest module.
4. **Execute TG 01.5 — Claimify Skill.** Create `.claude/skills/claimify.md`.

**Phase plan:** `project-management/phase-plans/phase-01-foundation-and-core-pipeline.md`

---

## Current Context

### Upstream relationship

| Remote     | URL                                         | Push |
| ---------- | ------------------------------------------- | ---- |
| `origin`   | `https://github.com/Robs-Git-Hub/ClaimeAI` | Yes  |
| `upstream` | `https://github.com/BharathxD/ClaimeAI`    | Blocked (`no_push_allowed`) |

### What the repo currently looks like

Still in original monorepo form:
- `apps/agent/` — Python LangGraph fact-checking backend (the part we keep)
- `apps/web/` — Next.js frontend (to be removed)
- `apps/extension/` — Chrome extension (to be removed)
- Root pnpm/Turborepo config (to be removed)

### Required API keys (not yet configured)

- `OPENAI_API_KEY` — for existing pipeline
- `EXA_API_KEY` — for web search evidence retrieval
- `OPENROUTER_API_KEY` — to be added in TG 01.3
- `REDIS_URI` — local Redis for LangGraph

### Key decisions made

1. **Keep OpenAI, add OpenRouter** — not a swap, a second option
2. **PDF ingest via Docling** — reuse doc-rag-backend's process
3. **Argument chain verification is Phase 02** — integrates with Obsidian vault argument pyramids from article-writer-research-of-agents

### Related repos

- **doc-rag-backend** — Docling PDF extraction (Mac only, not cloned on Windows)
- **article-writer-research-of-agents** — argument pyramid pipeline (Phase 02 integration point)
- **control-hub-building** — REPO note at `REPO-ClaimeAI.md`

---

## Recent Sessions

| Date       | What was done                                                    |
| ---------- | ---------------------------------------------------------------- |
| 2026-07-22 | Session 1: Fork, clone, PM setup, assessment artifact, websearch-and-costs doc |
