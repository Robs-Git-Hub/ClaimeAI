# Session Handover

**Last Updated:** 2026-07-25 (Session 16, outgoing)
**Current Status:** Phases 01–05 COMPLETE. Phase 06 DEFERRED (D60).

---

## Start Here

**Outgoing session completed:** Session 16 — Cross-repo usage documentation and HANDOVER cleanup. No pipeline code changes.

- Created `docs/playbook/cross-repo-usage.md` — how to run ClaimeAI from another repo (both light and heavy profiles, all flags, output format, verdicts)
- Updated `/claimify` skill — now covers both profiles, cross-repo section, `version: 1.0.0` frontmatter
- Created `control-hub-building/docs-meta/07-02-playbook-fact-checking-with-claimeai.md` — agent-facing guide with concrete paths
- Backed up claimify skill to `claude-multi-repo-instructions-and-lessons/skills/claimify/` and registered in `agent-sync-manifest.json`
- All four documents carry a 4-way sync note
- Trimmed HANDOVER.md from 222→~70 lines (was duplicating CLAUDE.md, phase plans, git history)

**Next task:** Decide what to work on — the pipeline is functionally complete (523 tests, live-verified cascade). Options:

1. Use the pipeline on real work (fact-check a draft using `docs/playbook/cross-repo-usage.md`)
2. Phase 07 (deep research commissions) or Phase 08 (draft update loop)
3. PixSerp integration as a cheap Exa alternative (narrow scope)
4. Buy Exa credits (committed config default is `exa`; 402 errors clear once account has credit; Tavily free tier fallback)

**Full plans:** `project-management/phase-plans/` (01–05 all COMPLETE). Phase 06 decision record: `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md`.

---

## Environment Status

| Component | Status | Notes |
|-----------|--------|-------|
| Python | 3.11.15 via uv | |
| Poetry | 2.4.1 | `uv tool install poetry` |
| Venv | `C:\vpy\claime-agent-j1KWVyi4-py3.11` | |
| Dev server | `poetry run dev` | Light profile only; heavy runs in-process |
| Tests | 523 (520 fast, 3 slow) | `pytest -m "not slow"` |
| Exa | Exhausted (402) | Buy credits or switch to Tavily |

---

## Operational Gotchas

- `--vault` path must be the vault **ROOT** (e.g. `vault-main`), NOT `vault-main/v-research` — `load_vault()` appends `v-research` internally. Wrong path silently produces zero vault notes.
- `--argument-pyramid` must match vault frontmatter exactly. Current real vault value: `un-ukraine-russia-war-votes-working-paper`.
- Real-vault command (4 corpus papers): `poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-cited-test.md --vault "PATH/vault-main" --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids d_o3qBk5fESO_q,d_7ZUo22uPGdsf,d_7lRaRsrtAJOW,d_ZikkNbPZFWWV`
- Cross-repo usage guide: `docs/playbook/cross-repo-usage.md`
- 4-way sync: claimify skill, cross-repo playbook, control-hub-building playbook, multi-repo backup — update all when changing any.

---

## Recent Sessions

| Session | Date | What was done |
|---------|------|---------------|
| 16 | 2026-07-25 | Cross-repo usage playbook, `/claimify` skill update (both profiles), multi-repo backup+manifest, HANDOVER trim. |
| 15 | 2026-07-25 | Phase 06 DEFERRED. Market scan (7 providers). PixSerp evaluated (32 live calls). Query-design playbook. crawl4ai documented. |
| 14 | 2026-07-25 | Phase 06 prep — comparator set, integration surface, evaluation metrics, Fable+goal-loop approach. |
| 13 | 2026-07-25 | Backlog maintenance — 4 fixes (zero-evidence verdicts, web-call counter, triage recalibration, Zeng corpus ID). +32 tests → 523. |
| 12 | 2026-07-25 | Phase 05 CLOSED. D10 amendment, alias resolution, conflict-demo, cited-file run. Exa exhausted. |
| 11 | 2026-07-25 | Phase 05 TGs 05.1–05.4. Cascade, citation-scoping, cross-checks, conflicts. |
| 10 | 2026-07-25 | Phase 04 CLOSED. Phase 05 designed. |

**Earlier sessions (1–9):** See git history. Covered: fork/setup, flatten, OpenRouter, PDF ingest, config extraction, Phase 02 vault verification, Phase 03 triage, Phase 04 corpus.

---

## Notes for Next Session

- Phase 06 future build = Serper SERP + crawl4ai two-stage (decision record in phase-plan-notes).
- D59: Fable + goal-loop evaluation approach unchanged when Phase 06 resumes.
- Claim 3 ground truth ambiguity: Feb 2025 UNGA had multiple resolutions; "98 votes" may be correct for A/RES/ES-11/9.
- Hetzner/doc-rag-backend: server healthy, 4 papers ingested, SSH on port 49152. Details in sibling repo.
- Commits pending in `control-hub-building` and `claude-multi-repo-instructions-and-lessons` for this session's cross-repo changes.
