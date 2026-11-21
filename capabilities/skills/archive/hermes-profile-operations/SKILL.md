---
name: hermes-profile-operations
description: Use when auditing or migrating Hermes profiles safely.
tags: [hermes, profiles, audit, migration, schemas, artifacts]
metadata:
  hermes:
    tags: [hermes, profiles, audit, migration, schemas, artifacts]
---

# Hermes Profile Operations

Use this class-level skill for read-only profile audits and structural migrations. Keep profile identity, runtime layout, artifact contracts, and production evidence separate so a clean-looking package is not mistaken for a tested system.

## Audit workflow

1. Inventory the live profile directories, `profile.yaml`, `config.yaml`, workflow manifests, skills, runtime, schemas, tests, and representative job artifacts, because diagrams and stale documentation are not live state.
2. Resolve the process that actually serves the profile, including `ExecStart`, interpreter, working directory, and `HERMES_HOME`, because the PATH CLI and active gateway can use different installations.
3. Compare the contract surface and check frontmatter/package names, duplicate config sections, twin schemas, and stale paths, because rename drift creates split-brain behavior.
4. Run deterministic tests and inspect job state before judging readiness, because paper-complete contracts and passing self-tests do not prove that a paid or delivery path executed.
5. Report strengths, ranked risks, and next actions with evidence such as test output, artifact hashes, job states, and capability results; never print secrets.

## Canonical migration layout

Keep `SOUL.md`, profile/config files, one canonical skill copy, `runtime/`, `workflow/`, `schemas/`, `tests/`, and `workspace/jobs/` in distinct roles. Workspace data must not become a second source tree. Compare duplicate packages before removing one, move runtime/config/schema files rather than copy-and-leave-both, then search the whole profile for runtime-valid old paths.

## Artifact and delivery gates

Use one validator/writer: generate → validate → normalize only documented aliases → validate again → hash → atomic persist → mark the stage validated. Carry an explicit `schema_version`, reject legacy shapes unless migration is requested, and keep analysis contact sheets distinct from provider references through explicit asset roles and hashes. For remote delivery, probe required capabilities, write, read back the exact result, write `RESULT`, read it back, then set and verify `FINISHED`; a local render never proves remote delivery.

## Verification

Compile affected modules, run no-provider self-tests, validate representative and deliberately invalid artifacts, test legacy detection, exercise deterministic media sampling and role separation, probe the delivery adapter, search for old paths, and rescan empty directories after tests. Report the remaining empty-directory count explicitly.

Exact checklists and historical recipes are routed in `references/curator-profile-archive-routes.md`.
