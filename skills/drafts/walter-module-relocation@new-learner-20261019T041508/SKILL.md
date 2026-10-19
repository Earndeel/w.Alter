---
name: walter-module-relocation
description: Use when implementing or validating journalled relocation of Walter modules with compatibility symlinks, interruption recovery and rollback.
---

# Validate module relocation

## Establish the implementation and scope

Read `/opt/walter-core/modules/catalog.json` and its referenced module contracts. Account for modules sharing a physical root; do not move that root twice. Reject overlapping destination trees and moves across filesystems.

The session produced staged candidates at `work/v1-harness/core/walter_platform/layout.py` and `work/v1-harness/core/tests/test_layout.py`. Locate the current implementation before using these paths. The candidate passed 25 targeted tests; production migration was not performed.

Back up before changing deployed files. Keep development and verification in an isolated fixture root. Do not execute module code, migrations or service activation during relocation.

## Validate paths and compatibility links

Require canonical absolute paths. Explicitly reject traversal, filesystem root and double-slash anchors: `Path(value).is_absolute()` alone accepts paths anchored at `//`. Check `Path(value).anchor == '/'`, normalized spelling and absence of `..`.

Reject unexpected symlink parents and pre-existing destination conflicts. Preserve source bytes, modes and symlink targets through same-filesystem renames. Install compatibility links through a temporary sibling link followed by atomic replacement.

Do not rely solely on inode identity to detect replacement of a compatibility link: unlinking and recreating a link can reuse its inode. Include an adversarial link-replacement test.

## Define rollback fingerprints explicitly

Protect file contents, permissions, symlink targets and unexpected additions. Validate all protected state before rollback makes its first mutation; refuse rollback if a human changed protected state.

Inventory mutable exclusions in both the plan and journal. The candidate used these exact exclusions:

- Everywhere: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.cache`.
- browse: `state`.
- skills: `skills`, `drafts`, `archive`, `reports`, `.worktrees`, `.git`.
- soul: `.state`, `build`.
- colab: `locks`, `evidence`.

These exclusions affect fingerprints only; preserve their contents during renames. Keep contracts, catalogue and registry protected even beneath an excluded directory. Do not automatically exclude virtual environments, dependencies, models or other configuration. Reassess exclusions against current module behavior.

## Verify before rollout

From the staging directory containing `work/v1-harness/core`, run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=work/v1-harness/core /root/.hermes/hermes-agent/venv/bin/python -m pytest -q -p no:cacheprovider work/v1-harness/core/tests/test_layout.py
```

Cover nested destinations, shared roots, repeated application, interruption recovery, exact permission restoration and rollback refusal after byte, mode, link or new-file changes. Assert refusal occurs before any write. Verify allowed mutable activity does not prevent rollback and protected metadata remains checked inside exclusions.

Review the plan and its exclusion inventory before any production mutation. Passing fixture tests demonstrates candidate behavior; it does not establish that services tolerate live relocation.
