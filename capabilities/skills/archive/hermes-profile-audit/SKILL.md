---
name: hermes-profile-audit
category: devops
description: "Use when auditing a Hermes profile end to end."
tags: [hermes, profiles, audit, review, multi-agent]
version: 1.0.0
author: W.Alter (curator)
license: private
metadata:
  hermes:
    tags: [hermes, profiles, audit, review, multi-agent]
    related_skills: [hermes-multi-agent-profiles, coder-profile, research-profile, media-buyer-profile]
---

# Hermes Profile Audit

## When to Use

- Monsieur asks to "analyze / review / audit" a Hermes profile ("notre profil X", "ce qu'on en pense").
- Before promoting a profile from DEV to production use.
- After a package rename or migration, to sweep for drift.

Read-only methodology for auditing a single Hermes profile (e.g. creative-factory, hephaestus, prometheus) and producing a strengths/weaknesses/recommendations report. For multi-profile orchestration architecture itself, see `hermes-multi-agent-profiles`.

## Method (summary)

Work cheapest-first; the full worked recipe with commands is in `references/profile-audit-checklist.md`:

1. **Inventory & identity** — `ls ~/.hermes/profiles/`, profile.yaml, config.yaml (validate YAML; note model/provider, toolsets, disabled_toolsets, profile-specific feature sections).
   - **Runtime identity gate:** resolve the process that actually serves the profile (`hermes gateway status`, active service, MainPID, `ExecStart`, interpreter, working directory, and `HERMES_HOME`). Compare it with `readlink -f "$(command -v hermes)"`; the CLI on `PATH` and the active gateway may use different installations and therefore different defaults. Resolve the merged configuration with the service's interpreter, not from the CLI alone.
   - For any context/payload feature, distinguish raw YAML, merged runtime value, production call-site, and real provider wire evidence. A configured key or passing helper tests do not prove that the active loop sends the feature.
2. **Contract surface** — README, SOUL.md, orchestrator contract, workflow manifest (stages, gates, schemas). Check rename drift: frontmatter `name:` must match package name.
3. **Body of work** — file census, `wc -l` ratio of deterministic runtime to prose, schema twins (singular/plural duplicates).
4. **Tests** — pytest + self-test scripts; confirm self-tests submit no paid jobs before running.
5. **Live usage** — state.db via Python `sqlite3` module (sqlite3 CLI absent): sessions, token counts, dead 0-message sessions.
6. **Jobs evidence** — `workspace/jobs/*/work/state.json`: statuses, `*_submitted` flags, blockers.
7. **Ops dependencies** — credential source of truth (vault), .env perms, proxy workarounds, shared adapters. Never print secret values.

## Key audit judgments

- **Paper-complete ≠ battle-tested.** A profile can have a perfect contract, passing deterministic tests, and clean self-tests while its paid/critical path has never executed (all jobs `submitted: false`, delivery loop never finished). This is the #1 risk to surface: the first real paid run is the true test. Always check jobs evidence before praising readiness.
- **Monoculture check.** A capability registry (e.g. video models) with exactly one entry makes "AUTO selection" nominal — no real choice, no fallback. Flag it.
- **Rename drift trio.** After a package rename, sweep for: stale frontmatter `name:`, duplicated config sections (old + new keys pointing at the same paths), twin schema files.
- **Config-vs-manifest inconsistency.** Same default (mode, qa_mode, timeouts) differing between workflow manifest and config.yaml is either intentional or drift — surface it, don't guess.
- **Unfinished loops.** `LOCAL_DELIVERABLE_READY_*_BLOCKED` states: local artifact verified, remote write-back/verify/FINISHED never completed once. Distinguish "designed" from "done".

## Report shape

Strengths (each backed by evidence: test output, job state, artifact hash) → weaknesses/risks ranked → recommendations ranked by value (real end-to-end paid run first, registry diversification second, delivery loop third, cosmetic cleanup last) → one-line honest verdict. Offer the obvious next action without pushing.

## Pitfalls

- `hermes-multi-agent-profiles` is PINNED — autonomous edits are refused; route profile-architecture learnings here instead.
- Do not trust the architecture diagram in any SKILL.md as live state; enumerate `~/.hermes/profiles/` directly.
- state.db schema: query `PRAGMA table_info(sessions)` before assuming column names.
