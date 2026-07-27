# Session Handover

**Last Updated:** 2026-07-27 (Session 17, outgoing)
**Current Status:** Phases 01–05 COMPLETE. Phase 06 DEFERRED (D60).

---

## Start Here

**Outgoing session completed:** Session 17 — Global `/fact-check` skill, `--research-dir` CLI flag, vault requirements reference.

- Created global skill `~/.claude/skills/fact-check/` — any repo can invoke ClaimeAI by declaring a `## Fact-Checking` section in its CLAUDE.md (vault_path, research_dir, argument_pyramid, corpus_ids)
- Added `--research-dir` flag to `run_heavy.py` + `ResourceManifest.research_dir` field — vaults no longer require `v-research/` as the subfolder name (default unchanged)
- Wrote `references/vault-requirements.md` — full spec of what the pipeline expects from a vault (frontmatter fields, note naming, link traversal, type filtering, silent degradation modes)
- Platform-aware skill (Windows + macOS paths) — backed up to multi-repo with manifest entry
- 520 tests pass

**Incoming session — Mac setup task:**

Copy the global fact-check skill from the multi-repo backup to the Mac's global skills directory:
```bash
cp -r ~/Documents/GitHub/Robert-Repos/claude-multi-repo-instructions-and-lessons/skills/fact-check \
      ~/.claude/skills/fact-check
```
This installs `/fact-check` globally so it works from any repo on the Mac.

**Next task:** Decide what to work on — the pipeline is functionally complete (523 tests, live-verified cascade). Options:

1. Use the pipeline on real work (fact-check a draft — the global `/fact-check` skill is ready)
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
| 17 | 2026-07-27 | Global `/fact-check` skill (platform-aware, CLAUDE.md config). `--research-dir` CLI flag. Vault requirements reference. |
| 16 | 2026-07-25 | Cross-repo usage playbook, `/claimify` skill update (both profiles), multi-repo backup+manifest, HANDOVER trim. |
| 15 | 2026-07-25 | Phase 06 DEFERRED. Market scan (7 providers). PixSerp evaluated (32 live calls). Query-design playbook. crawl4ai documented. |
| 13 | 2026-07-25 | Backlog maintenance — 4 fixes (zero-evidence verdicts, web-call counter, triage recalibration, Zeng corpus ID). +32 tests → 523. |
| 12 | 2026-07-25 | Phase 05 CLOSED. D10 amendment, alias resolution, conflict-demo, cited-file run. Exa exhausted. |

**Earlier sessions (1–11):** See git history.

---

## Notes for Next Session

- Phase 06 future build = Serper SERP + crawl4ai two-stage (decision record in phase-plan-notes).
- D59: Fable + goal-loop evaluation approach unchanged when Phase 06 resumes.
- Claim 3 ground truth ambiguity: Feb 2025 UNGA had multiple resolutions; "98 votes" may be correct for A/RES/ES-11/9.
- Hetzner/doc-rag-backend: server healthy, 4 papers ingested, SSH on port 49152. Details in sibling repo.
