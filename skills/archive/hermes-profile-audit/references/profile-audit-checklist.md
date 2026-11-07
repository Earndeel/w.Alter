# Profile Audit Checklist — worked recipe (creative-factory audit, Aug 2026)

Read-only audit order, cheapest first. Produces a strengths/weaknesses/recommendations report.

## 1. Inventory & identity
- `ls -la ~/.hermes/profiles/` — ground truth for what exists (any SKILL.md architecture diagram is an example, not live state).
- `cat <profile>/profile.yaml` — description.
- `cat <profile>/config.yaml` — validate with `python3 -c "import yaml; yaml.safe_load(open(...))"`; note model/provider, toolsets + platform_toolsets, disabled_toolsets count, agent limits, compression tuning, profile-specific feature sections.

## 2. Contract surface
- README.md, SOUL.md, ORCHESTRATOR_CONTRACT.md (or equivalent).
- Workflow manifest (e.g. workflow/workflow.yaml): stages, inputs/outputs, output schemas, gates, validation sequence.
- Rename-drift check: frontmatter `name:` must match the package/directory name.

## 3. Body of work
- `find skills workflow schemas scripts runtime tests -type f` + `du -sh` per dir.
- `wc -l` across SKILL.md / runtime/*.py / tests/*.py — ratio of deterministic runtime to prose.
- Schema census: count files, spot twins (e.g. `contact_sheet_manifest` vs `contact_sheets_manifest` — singular/plural duplicates left by renames).

## 4. Tests (local/deterministic only)
- `python3 -m pytest tests/ -q`.
- Self-test script if present (e.g. `tests/self_test.py`) — confirm it submits no paid jobs before running.

## 5. Live usage from state.db
sqlite3 CLI absent → use Python `sqlite3` module.
- `sessions`: id, title, model, message_count, input/output tokens, estimated_cost_usd.
- `messages`: COUNT(*), MIN/MAX timestamps.
- Sessions with 0 messages = dead cruft (safe cleanup candidates).
- Query `PRAGMA table_info(sessions)` before assuming column names.

## 6. Jobs evidence — paper vs reality
- `workspace/jobs/*/work/state.json`: status, stage, completed_stages, `*_submitted` flags, blockers.
- Key distinction: a profile can be paper-complete (perfect contract + passing deterministic tests) while its paid/critical path has NEVER executed (all jobs show `submitted: false`, or delivery blocked). Flag that as the #1 risk — the first real paid run is the true test.

## 7. Ops dependencies
- Dependency notes (*.md at profile root): credentials source of truth (vault), .env binding + perms 0600, proxy workarounds (e.g. SOCKS via SSH relay when a provider edge blocks the VPS IP), shared adapters.
- Never print secret values during audit; check presence/length only.

## 8. Recurring finding patterns to sweep for
- **Rename drift trio**: stale frontmatter `name:`, duplicated config sections (old + new key blocks pointing at same paths), twin schema files.
- **Config-vs-manifest default inconsistency** (e.g. qa_mode FULL in workflow.yaml, OFF in config.yaml) — intentional or drift, make it explicit in the report.
- **Model-registry monoculture**: selection_mode AUTO with exactly one registered model = no real selection, no fallback.
- **Unfinished delivery loop**: local artifact ready but remote write-back/verify/FINISHED never completed once.

## 9. Report shape
Strengths (each backed by evidence: test output, job state, artifact hash) → weaknesses/risks ranked → recommendations ranked by value → honest one-line verdict. Offer the obvious next action (e.g. minimal paid smoke mission) without pushing.

## Worked example findings (creative-factory v1.3, Aug 2026)
- Strengths found: IMAGE/VIDEO/POST routing principle; lazy_upstream_only context discipline; real gates (pregen fingerprints, re-hash before provider calls); 8 pytest pass; self-test covering 9 stages with resume check on 21 artifacts; Kie edge 403/1010 solved via SSH SOCKS proxy through the Mac without exposing the key.
- Weaknesses found: single-model video registry (grok-imagine-video-1-5-preview only); all jobs `video_generation_submitted: false`; delivery loop blocked (`LOCAL_DELIVERABLE_READY_EXTERNAL_DELIVERY_BLOCKED`); rename drift (`name: video-agent` in contract frontmatter, duplicated `video_agent:` + `creative_factory:` config sections, twin contact-sheet schemas); qa_mode FULL vs OFF inconsistency between manifest and config.
