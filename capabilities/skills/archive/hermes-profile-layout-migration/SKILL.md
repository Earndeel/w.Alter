---
name: hermes-profile-layout-migration
category: devops
version: 1.0.0
author: W.Alter
license: internal
description: "Use when migrating Hermes profile layouts safely."
tags: [hermes, profiles, migration, schemas, artifacts, filesystem]
related_skills: [hermes-multi-agent-profiles, hermes-agent-update, hermes-session-db]
metadata:
  hermes:
    tags: [hermes, profiles, migration, schemas, artifacts, filesystem]
    related_skills: [hermes-multi-agent-profiles, hermes-agent-update, hermes-session-db]
---

# Hermes Specialized Profile Layout Migration

## When to Use

Use when a specialized Hermes profile has accumulated duplicated skills, runtime code inside a job workspace, stale schemas, legacy artifact contracts, hardcoded old paths, or empty directory trees after a migration. This is a structural migration skill, not a feature-refactor skill.

## Scope discipline

Preserve the profile's existing functional workflow and APIs unless the requested migration requires a contract fix. Do not use the migration as an excuse to redesign model routing, add a new workflow stage, create a tenth skill, clean unrelated caches, or rewrite stable artifact names without a concrete compatibility reason.

## Canonical layout

Prefer this separation:

```text
profile/
├── SOUL.md / config.yaml / profile.yaml
├── skills/<skill-name>/SKILL.md     # one canonical copy per functional skill
├── runtime/                         # executable code and adapters
├── workflow/                        # workflow/defaults/model registries
├── schemas/                         # authoritative JSON schemas
├── tests/                           # tests and representative fixtures
└── workspace/jobs/                  # persisted mission data only
```

`workspace/` must not contain executable source, canonical skills, canonical schemas, or business configuration. Move files physically; do not leave a second copy behind.

## Migration sequence

1. Inventory the profile tree, duplicated skill sets, runtime modules, config/workflow files, schemas, tests, hardcoded paths and representative artifacts.
2. Compare each duplicate skill before deletion. Preserve the newest rule set and merge functional improvements; check especially for brand/copy minimal-diff rules and gate semantics.
3. Move runtime, workflow/config and schema files to profile-level directories. Update imports, subprocess paths, loaders, config, documentation, scripts and persisted path references. Delete the obsolete tree only after an exhaustive search.
4. Define one canonical contract per structured artifact. Use an explicit `schema_version` and a central validator. Do not weaken a schema merely to accept stale fixtures.
5. Enforce the artifact write sequence: generate → validate → normalize only documented aliases → validate again → hash → atomic persist → mark the stage validated.
6. Reject legacy artifacts on resume unless an explicit deterministic migration is requested. If the old shape cannot be migrated safely, recalculate only the producing stage rather than silently interpreting it as current data.
7. Keep analysis evidence and generation inputs role-labelled. Contact sheets are analysis/QA assets; individual frames, panels and references are generation assets. Consumers select by role and verify hashes, never by “last PNG”.
8. For external delivery, use the profile's canonical adapter. Probe all required read/write capabilities at the start of a mission, write remotely, read back the exact result, then persist `RESULT`; only then set `FINISHED=true`.
9. Audit empty directories bottom-up. Keep a directory only when code explicitly requires it before execution and cannot create it dynamically. Prefer `mkdir(..., parents=True, exist_ok=True)` at the write site. Remove empty historical job/runtime/cache/log trees and verify recursively that zero unnecessary empty directories remain.

## Verification gates

Run all of these before declaring the migration complete:

- compile/import every affected Python module;
- run the existing self-test without paid provider calls;
- validate representative real artifacts for every canonical schema;
- test a deliberately invalid artifact and assert a localizable failure;
- test legacy detection and explicit migration/recalculation;
- exercise deterministic media sampling and contact-sheet pagination;
- assert analysis-only assets cannot enter generation references;
- probe external capabilities and test the failure path;
- when a safe test adapter/destination exists, verify write → read → RESULT → FINISHED;
- search the whole profile for old layout paths and confirm no runtime-valid reference remains;
- rescan directories after tests and report `EMPTY DIRECTORIES REMOVED` plus the remaining count.

## Pitfalls

- Copying the new runtime while leaving the old package tree active creates split-brain behavior; move and delete, then audit.
- Treating a v1.2 artifact as v1.3 because its keys look similar silently corrupts resume semantics.
- Making schemas permissive to pass artificial fixtures hides producer/consumer drift; fixtures must be representative of actual pipeline output.
- A contact sheet can be excellent VLM evidence and still be a poor provider input; encode that distinction in asset roles and enforce it in the consumer.
- A successful local render is not a verified remote delivery. `FINISHED` is a remote transaction result, not a local file status.
- Removing every empty directory without checking Hermes startup behavior can break first-write paths; establish dynamic creation or an explicit precondition first.

## Reference

See `references/specialized-profile-layout-migration.md` for the tested v1.3 migration details, validation contract examples, deterministic forensics parameters, Google delivery probe, and empty-directory cleanup record.
