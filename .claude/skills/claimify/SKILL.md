---
name: claimify
description: Fact-check a PDF or text/markdown file end-to-end with this repo's LangGraph pipeline (claim extraction + web-verified claims). Trigger on "fact-check this file/PDF", "/claimify", or "run claimify on <path>".
---

# Claimify

Runs `scripts/run_from_pdf.py` against a PDF, `.md`, `.markdown`, or `.txt`
file, then summarizes the resulting fact-check report for the user. This
skill only orchestrates the existing pipeline — it does not call any LLM or
search API directly.

## 1. Resolve the input file

- If the user gave a path, use it (PDF, `.md`, `.markdown`, or `.txt`).
- If no path was given, look for the newest PDF in `workspace/inbox/`.
  - If `workspace/inbox/` has no PDFs either, ask the user for a path before
    doing anything else.

## 2. Preflight: environment

Check for a `.env` file at the repo root (do not print the values of any
key — only whether they are present/non-empty):

- `OPENAI_API_KEY` must be present (starts with `sk-proj-`).
- `EXA_API_KEY` must be present.
- If `LLM_PROVIDER=openrouter` is set, `OPENROUTER_API_KEY` must also be
  present (starts with `sk-or-`).

If anything required is missing, stop and tell the user exactly which
variable(s) to add to `.env` (see `.env.example` for the expected format).
Do not attempt to run the pipeline with missing keys.

## 3. Preflight: server

The pipeline talks to a LangGraph dev server at `http://127.0.0.1:2024`
(the default `--url` for `scripts/run_from_pdf.py`).

- Check whether it's already up, e.g. `GET http://127.0.0.1:2024/assistants/fact_checker`
  (or any lightweight request against that base URL / the langgraph_sdk
  client). A connection error means it's not running.
- If it's not running, start it as a background task:
  `poetry run dev`
  (this auto-downloads NLTK punkt data and uses `--allow-blocking` which
  the synchronous NLTK tokenizer requires). Wait for its startup output
  (log lines mentioning registering the graph / the server being ready on
  port 2024) before proceeding. Don't run it in the foreground — it stays
  up for the whole session.

## 4. Run the pipeline

```
poetry run python scripts/run_from_pdf.py <path>
```

Useful tuning flags (mention if the user asks, or if a first run needs
adjusting):

- `--max-chars` — max characters per section sent to the graph (default 4000)
- `--min-chars` — sections smaller than this get merged into a neighbor (default 200)
- `--url` — override the server URL if it's not on the default port

**Cost and time warning — tell the user before running on a large document:**

- This costs real API money: Exa search is roughly **$0.007–$0.035 per
  claim**, plus LLM costs (extraction, verification, evidence evaluation)
  on top of that per claim as well.
- On a brand-new machine, the *first* PDF run also downloads Docling's
  layout models (several hundred MB) — after that they're cached and
  extraction is fast. Text (`.md`/`.txt`) inputs skip Docling entirely.
- Long papers can take many minutes end-to-end (multiple sections, each
  with up to 5 search iterations per claim if evidence is insufficient).
- **Suggest starting small**: point this at a short section, or a 1–2
  paragraph `.txt`/`.md` file with a couple of clear factual claims, to
  sanity-check the setup before spending money on a full document.

## 5. Present results

Read `workspace/output/<stem>/report.md` (and `results.json` if more detail
is needed) and give the user a concise summary:

- Total sections checked.
- Verdict counts across the whole run (Supported / Refuted / Insufficient /
  Conflicting), broken out per section if that's more useful.
- Call out any **Refuted** claims by name — these are the most actionable.
- Link both output files:
  - `workspace/output/<stem>/report.md`
  - `workspace/output/<stem>/results.json`

## 6. Failure modes

- **Server not running / connection refused** — start it per step 3, don't
  just report the error.
- **Missing API key(s)** — name the exact env var(s) missing, per step 2.
- **Per-section errors** — `scripts/run_from_pdf.py` records failed
  sections in `results.json` (and `report.md`) with an `error` field instead
  of silently dropping them. Surface these to the user; don't hide them or
  claim the whole run succeeded if some sections failed.
- **Unsupported file type** — only `.pdf`, `.md`, `.markdown`, `.txt` are
  supported; the script will exit with a clear message naming the supported
  extensions if given anything else.
