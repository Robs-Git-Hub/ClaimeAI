---
name: claimify
version: 1.0.0
description: Fact-check a PDF or text/markdown file end-to-end with this repo's LangGraph pipeline (claim extraction + web-verified claims). Trigger on "fact-check this file/PDF", "/claimify", or "run claimify on <path>".
---

# Claimify

Runs the fact-checking pipeline against a PDF, `.md`, `.markdown`, or `.txt`
file, then summarizes the resulting fact-check report for the user.

> **Sync note:** Four copies must be kept in sync. When updating any, update all:
> 1. This skill (ClaimeAI `.claude/skills/claimify/SKILL.md`) — canonical source
> 2. `docs/playbook/cross-repo-usage.md` (ClaimeAI) — cross-repo playbook
> 3. `control-hub-building/docs-meta/07-02-playbook-fact-checking-with-claimeai.md`
> 4. `claude-multi-repo-instructions-and-lessons/skills/claimify/SKILL.md` — versioned backup

## Choose the profile

| Profile | Entry point | When to use |
|---------|-------------|-------------|
| **Light** | `scripts/run_from_pdf.py` | Web-only verification. No vault, no corpus. Quick checks. |
| **Heavy** | `scripts/run_heavy.py` | Full pipeline: vault + triage + corpus + web cascade. Papers with an Obsidian vault. |

Default to **light** unless the user specifies a vault, corpus IDs, or asks
for heavy/full verification. If the input file contains wikilinks (`[[...]]`)
and the user has a vault, suggest heavy.

## 1. Resolve the input file

- If the user gave a path, use it (PDF, `.md`, `.markdown`, or `.txt`).
- If no path was given, look for the newest PDF in `workspace/inbox/`.
  - If `workspace/inbox/` has no PDFs either, ask the user for a path before
    doing anything else.

## 2. Preflight: environment

Check `config.toml` at the repo root for `llm_provider` (under `[pipeline]`),
then check `.env` for the required API keys (do not print key values — only
whether they are present/non-empty):

- If `llm_provider = "openai"` (default): `OPENAI_API_KEY` must be in `.env` (starts with `sk-proj-`).
- If `llm_provider = "openrouter"`: `OPENROUTER_API_KEY` must be in `.env` (starts with `sk-or-`).
- `EXA_API_KEY` must be present (or `TAVILY_API_KEY` if `search_provider = "tavily"` in `config.toml`).
- For heavy profile with `--corpus-ids`: `RAG_API_KEY` must be present.

If anything required is missing, stop and tell the user exactly which
variable(s) to add to `.env` (see `.env.example` for the expected format).
Do not attempt to run the pipeline with missing keys.

## 3. Preflight: server (light profile only)

The light pipeline talks to a LangGraph dev server at `http://127.0.0.1:2024`.
The heavy pipeline runs in-process and does **not** need the server.

- Check whether it's already up, e.g. `GET http://127.0.0.1:2024/assistants/fact_checker`
  (or any lightweight request against that base URL). A connection error means
  it's not running.
- If it's not running, start it as a background task:
  `poetry run dev`
  Wait for its startup output (log lines mentioning the server being ready on
  port 2024) before proceeding.

## 4. Run the pipeline

### Light profile

```
poetry run python scripts/run_from_pdf.py <path>
```

Flags:
- `--max-chars` — max characters per section (default 4000)
- `--min-chars` — sections shorter than this merge into a neighbor (default 200)
- `--url` — override the server URL if not on default port

### Heavy profile

```
poetry run python scripts/run_heavy.py <draft-path> \
    --vault <vault-path> \
    --argument-pyramid <name> \
    --corpus-ids <d_id1,d_id2>
```

Flags:
- `--vault PATH` — Obsidian vault root (omit to skip vault verification)
- `--argument-pyramid NAME` — filter vault notes by this frontmatter value
- `--profile heavy|light` — default: heavy
- `--no-web` — disable web route (vault + corpus only)
- `--corpus-ids CSV` — comma-separated doc-rag-backend document IDs (omit to disable corpus route)

All paths can be absolute (for cross-repo use, they must be).

### Cross-repo use

When called from another repo, use absolute paths for the draft and vault.
See `docs/playbook/cross-repo-usage.md` for the full guide including how to
get corpus IDs and read output from another repo.

**Cost and time warning — tell the user before running on a large document:**

- This costs real API money: Exa search is roughly **$0.007–$0.035 per
  claim**, plus LLM costs per claim at each stage.
- Heavy profile with vault + corpus + web is the most expensive per claim.
- Long papers can take many minutes end-to-end.
- **Suggest starting small**: use a short section or 1–2 paragraph test file
  to sanity-check the setup before spending money on a full document.

## 5. Present results

Read `workspace/output/<stem>/report.md` (and `results.json` if more detail
is needed) and give the user a concise summary:

- Total sections/claims checked.
- Verdict counts across the whole run (Supported / Refuted / Insufficient /
  Conflicting), broken out per section if useful.
- For heavy profile: route summary (how many went through vault / corpus / web).
- Call out any **Refuted** or **contradicted** claims — these are most actionable.
- Highlight claims with `suggested_action` other than `NO_ACTION`.
- Link both output files:
  - `workspace/output/<stem>/report.md`
  - `workspace/output/<stem>/results.json`

## 6. Failure modes

- **Server not running / connection refused** (light profile) — start it per
  step 3, don't just report the error.
- **Missing API key(s)** — name the exact env var(s) missing, per step 2.
- **Per-section errors** — `run_from_pdf.py` records failed sections in
  `results.json` with an `error` field. Surface these to the user.
- **Unsupported file type** — only `.pdf`, `.md`, `.markdown`, `.txt` are
  supported.
