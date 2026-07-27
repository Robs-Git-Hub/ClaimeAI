# Session Handover

**Last Updated:** 2026-07-27 (Session 18, outgoing)
**Current Status:** Phases 01–05 COMPLETE. Phase 06 DEFERRED (D60).

---

## Start Here

**Outgoing session completed:** Session 18 — Mac environment setup, live smoke test, global skill install.

- Mac environment bootstrapped: Poetry 2.2.1 + Python 3.12, all deps installed, 520 tests pass (18s)
- langgraph-cli pinned to 0.4.8 (same version-compat fix as Windows — latest langgraph-api 0.11.x is incompatible with langgraph 0.4.x)
- Global `/fact-check` skill installed from multi-repo backup (cloned `Robert-Repos/claude-multi-repo-instructions-and-lessons` to Mac)
- Exa credits topped up — live smoke test passed: 3 Apollo 11 claims, all Supported via Exa search
- LangGraph dev server left running at `http://127.0.0.1:2024` (may need restart if Mac sleeps)

**Next task:** Decide what to work on — the pipeline is functionally complete (520 tests, live-verified on Mac). Options:

1. Use the pipeline on real work (fact-check a draft — the global `/fact-check` skill is ready)
2. Phase 07 (deep research commissions) or Phase 08 (draft update loop)
3. PixSerp integration as a cheap Exa alternative (narrow scope)

**Full plans:** `project-management/phase-plans/` (01–05 all COMPLETE). Phase 06 decision record: `project-management/phase-plan-notes/phase-06/phase-06-search-provider-decision.md`.

---

## Environment Status

| Component | Status | Notes |
|-----------|--------|-------|
| Python | 3.12.12 via Homebrew (Mac) | Windows: 3.11.15 via uv |
| Poetry | 2.2.1 (Mac) | Windows: 2.4.1 |
| Venv | `claime-agent-AcjO-nnN-py3.12` (Mac) | Windows: `C:\vpy\claime-agent-j1KWVyi4-py3.11` |
| Dev server | `poetry run dev` | Light profile only; heavy runs in-process |
| langgraph-cli | Pinned 0.4.8 | Latest (0.4.31) breaks with langgraph 0.4.x |
| Tests | 523 (520 fast, 3 slow) | `pytest -m "not slow"` |
| Exa | Active (credits topped up 2026-07-27) | Live-verified on Mac |

---

## Operational Gotchas

- `--vault` path must be the vault **ROOT**, not the research subdirectory — `load_vault()` appends `research_dir` (default `v-research`) internally. Wrong path silently produces zero vault notes.
- `--research-dir` overrides the subfolder name if the vault doesn't use `v-research/` (new in Session 17).
- `--argument-pyramid` must match vault frontmatter exactly. Current real vault value: `un-ukraine-russia-war-votes-working-paper`.
- Real-vault command (4 corpus papers): `poetry run python scripts/run_heavy.py workspace/inbox/ukraine-intro-cited-test.md --vault "PATH/vault-main" --argument-pyramid un-ukraine-russia-war-votes-working-paper --corpus-ids d_o3qBk5fESO_q,d_7ZUo22uPGdsf,d_7lRaRsrtAJOW,d_ZikkNbPZFWWV`
- Cross-repo usage guide: `docs/playbook/cross-repo-usage.md`
- 4-way sync: claimify skill, cross-repo playbook, control-hub-building playbook, multi-repo backup — update all when changing any.
- Global `/fact-check` skill vault requirements: `~/.claude/skills/fact-check/references/vault-requirements.md`

---

## Recent Sessions

| Session | Date | What was done |
|---------|------|---------------|
| 18 | 2026-07-27 | Mac environment setup (Python 3.12, langgraph-cli pin). Global `/fact-check` skill installed. Exa live-verified. |
| 17 | 2026-07-27 | Global `/fact-check` skill (platform-aware, CLAUDE.md config). `--research-dir` CLI flag. Vault requirements reference. |
| 16 | 2026-07-25 | Cross-repo usage playbook, `/claimify` skill update (both profiles), multi-repo backup+manifest, HANDOVER trim. |
| 15 | 2026-07-25 | Phase 06 DEFERRED. Market scan (7 providers). PixSerp evaluated (32 live calls). Query-design playbook. crawl4ai documented. |
| 13 | 2026-07-25 | Backlog maintenance — 4 fixes (zero-evidence verdicts, web-call counter, triage recalibration, Zeng corpus ID). +32 tests → 523. |
| 12 | 2026-07-25 | Phase 05 CLOSED. D10 amendment, alias resolution, conflict-demo, cited-file run. Exa exhausted. |

**Earlier sessions (1–11):** See git history.

---

## Notes for Next Session

- Mac dev server may need restart after sleep: `poetry run dev` from ClaimeAI directory.
- langgraph-cli MUST stay pinned at 0.4.8 — do NOT upgrade. Latest (0.4.31) pulls langgraph-api 0.11.x which is incompatible with langgraph 0.4.x (ImportError on CONFIG_KEY_CACHE).
- Multi-repo backup cloned to `~/Documents/GitHub/Robert-Repos/claude-multi-repo-instructions-and-lessons/` on this Mac.
- Phase 06 future build = Serper SERP + crawl4ai two-stage (decision record in phase-plan-notes).
- D59: Fable + goal-loop evaluation approach unchanged when Phase 06 resumes.
- Claim 3 ground truth ambiguity: Feb 2025 UNGA had multiple resolutions; "98 votes" may be correct for A/RES/ES-11/9.
- Hetzner/doc-rag-backend: server healthy, 4 papers ingested, SSH on port 49152. Details in sibling repo.
