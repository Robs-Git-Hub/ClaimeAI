# Cross-Repo Usage: Running ClaimeAI from Another Repo

> **Sync note:** Four copies must be kept in sync. When updating any, update all:
> 1. ClaimeAI `.claude/skills/claimify/SKILL.md` — canonical source
> 2. This playbook (`docs/playbook/cross-repo-usage.md`) — cross-repo reference
> 3. `control-hub-building/docs-meta/07-02-playbook-fact-checking-with-claimeai.md`
> 4. `claude-multi-repo-instructions-and-lessons/skills/claimify/SKILL.md` — versioned backup

## When to use which profile

| Profile | Entry point | Use case | Server needed? |
|---------|-------------|----------|----------------|
| **Light** | `scripts/run_from_pdf.py` | Web-only verification. No vault, no corpus. Good for quick checks on standalone text. | Yes — LangGraph dev server on port 2024 |
| **Heavy** | `scripts/run_heavy.py` | Full pipeline: vault + triage + corpus + web cascade. Use for papers with an Obsidian vault. | No — runs in-process |

## Prerequisites

### Environment variables (in ClaimeAI's `.env`)

| Variable | When required |
|----------|--------------|
| `OPENAI_API_KEY` | Always (default provider) |
| `EXA_API_KEY` | Always (default search provider) |
| `REDIS_URI` | Light profile only (LangGraph server uses it) |
| `RAG_API_KEY` | Heavy profile with `--corpus-ids` |
| `TAVILY_API_KEY` | Only if `search_provider = "tavily"` in config.toml |
| `OPENROUTER_API_KEY` | Only if `llm_provider = "openrouter"` in config.toml |

### Python environment

The ClaimeAI repo uses Poetry. From the ClaimeAI directory:

```bash
poetry install
```

### LangGraph dev server (light profile only)

The light profile talks to a LangGraph dev server. Start it from the ClaimeAI directory:

```bash
poetry run dev
```

Wait for the "ready on port 2024" log line. The heavy profile does **not** need this — it runs the graphs in-process.

## Running from another repo

All paths below are absolute. Replace the placeholders with your actual paths.

### Light profile (web-only)

```bash
python "C:\path\to\ClaimeAI\scripts\run_from_pdf.py" "C:\path\to\your-paper.md"
```

Optional flags:
- `--max-chars 4000` — max characters per section (default 4000)
- `--min-chars 200` — sections shorter than this merge into a neighbor (default 200)
- `--url http://127.0.0.1:2024` — override server URL if non-default

**Important:** This script must be run with ClaimeAI's Poetry environment. Either:
- `cd` to the ClaimeAI directory first and use `poetry run python scripts/run_from_pdf.py "C:\path\to\your-paper.md"`
- Or activate ClaimeAI's virtualenv and run with the absolute script path

### Heavy profile (vault + corpus + web cascade)

```bash
cd "C:\path\to\ClaimeAI"
poetry run python scripts/run_heavy.py "C:\path\to\your-paper.md" \
    --vault "C:\path\to\your-vault" \
    --research-dir "v-research" \
    --argument-pyramid "your-pyramid-name" \
    --corpus-ids "d_abc123,d_def456"
```

All flags:

| Flag | Required | Description |
|------|----------|-------------|
| `draft` (positional) | Yes | Path to the draft (`.md`, `.markdown`, `.txt`, `.pdf`) |
| `--vault PATH` | No | Obsidian vault root. Omit to skip vault verification entirely. |
| `--research-dir NAME` | No | Subdirectory under vault root containing `.md` notes (default: `v-research`). |
| `--argument-pyramid NAME` | No | Filter vault notes by this `argument_pyramid` frontmatter value |
| `--profile heavy\|light` | No | Default: `heavy`. Use `light` to run web-only through this entry point. |
| `--no-web` | No | Disable web route (vault + corpus only) |
| `--corpus-ids CSV` | No | Comma-separated doc-rag-backend document IDs. Omit to disable corpus route. |

### Getting corpus IDs

If your paper's sources are in doc-rag-backend (api.ragtogo.com), you need their document IDs for `--corpus-ids`. The pipeline's `list_documents()` function queries the API, but the easiest way is to check the doc-rag-backend admin or your upload records for the `d_*` IDs.

## Output

Both profiles write results to `ClaimeAI/workspace/output/<stem>/`:

| File | Contents |
|------|----------|
| `report.md` | Human-readable gap report with verdict tables, conflict flags, route summaries |
| `results.json` | Structured data: every ClaimRecord with verdicts, triage class, suggested actions |

The `<stem>` is the input filename without extension.

### Reading results from another repo

An agent in another repo should read the output files using their absolute paths:

```
C:\path\to\ClaimeAI\workspace\output\your-paper\report.md
C:\path\to\ClaimeAI\workspace\output\your-paper\results.json
```

### Key fields in results.json

Each claim record includes:
- `claim_text` — the extracted factual claim
- `triage_class` — how the claim was classified (general-factual, academic-citable, novel-result, trivial, etc.)
- `route_verdicts` — list of verdicts from each route that ran (vault, corpus, web)
- `suggested_action` — what to do next (VERIFY_EXTERNALLY, ADD_VAULT_NOTE, NO_ACTION, etc.)
- `importance` — 1–5 score from triage

### Verdict meanings

| Verdict | Meaning |
|---------|---------|
| `vault_supported` / `corpus_supported` / `Supported` | Evidence found that supports the claim |
| `vault_contradicted` / `corpus_contradicted` / `Refuted` | Evidence found that contradicts the claim |
| `not_supported` / `corpus_insufficient` / `Insufficient` | Not enough evidence either way |
| `no_vault_match` / `no_corpus_hits` | No relevant material found in that source |
| `Conflicting` | Different sources disagree |

## Cost and time

- **LLM costs:** Each claim goes through extraction (mid tier), optional triage (mid tier), optional evidence summarization (mid tier), and evaluation (high tier). Heavy profile with vault + corpus + web is the most expensive per claim.
- **Search costs:** Exa is ~$0.007–$0.035 per claim. Up to 5 search iterations per claim if evidence is insufficient (web route only).
- **Time:** Long papers can take many minutes. The heavy profile is slower than light because it runs more stages.
- **Recommendation:** Start with a small test file (2–3 claims) to verify setup before running on a full paper.

## For agents in other repos

If you are an AI agent working in a different repository and need to fact-check a paper:

1. Verify ClaimeAI's `.env` has the required API keys (check existence, never print values)
2. For heavy profile: no server needed — just `cd` to ClaimeAI and run `poetry run python scripts/run_heavy.py` with absolute paths
3. For light profile: check if the LangGraph dev server is running at `http://127.0.0.1:2024` first; start it if not
4. Read the output from `ClaimeAI/workspace/output/<stem>/report.md`
5. Focus on claims with `suggested_action` values other than `NO_ACTION` — those are the actionable findings
