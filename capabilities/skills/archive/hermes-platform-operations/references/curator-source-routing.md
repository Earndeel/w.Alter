# Curator source routing

The umbrella contains distilled class rules. Use an archive only for an exact historical recipe that is not represented here.

## Required lookup sequence

1. Refresh `skills_list` after compaction or an archive round.
2. Confirm the archive root with `skill_view(name='.archive/<old-name>')`.
3. Read the original `SKILL.md` or support file using the exact `file_path` returned by that archive lookup.
4. Verify current commands, paths, versions, and external state before applying a historical recipe.
5. Do not call the old unqualified name after it has been archived, and do not retry a failed read of a confirmed archive.

## Absorbed Hermes platform sources

- `.archive/hermes-config-extra-pitfall/` — adapter configuration under `extra`; use the archive only for the exact original examples.
- `.archive/hermes-dashboard-setup/` — dashboard/API-server setup, frontend build, tunnel, and theme details.
- `.archive/hermes-runtime-routing/` — model/provider/payload/cache/picker routing.
- `.archive/hermes-agentic-worker-integration/` — delegated worker seam, tool propagation, and provider-family validation.
- `.archive/async-provider-callbacks/` — callback, polling, idempotency, and artifact retrieval.
- `.archive/hermes-profile-audit/` and `.archive/hermes-profile-layout-migration/` — profile audit/migration details.
- `.archive/hermes-memory-ops/` and `.archive/memory-recall-injection/` — memory stack and recall injection details.
- `.archive/hermes-session-db/` — session SQLite and FTS details.
- `.archive/hermes-live-compaction-debugging/` — exact compaction boundary reproduction.
- `.archive/hermes-stack-update-resilience/` — update and custom-plugin survival checks.
- `.archive/hermes-nous-tool-gateway/` — Nous managed tool gateway details.
- `.archive/authenticated-workflows/` — authenticated browser, artifact, usage, and frontend QA details.
- `.archive/computer-use-operations/` — computer-use and remote GUI contracts.

Archive routes are pointers, not proof that historical behavior remains current. Re-verify live state at the umbrella's evidence boundary.
