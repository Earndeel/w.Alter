# walter-model-router — Which documentation is maintained, and the orchestrator note (2026-10-23).

Moved verbatim from SKILL.md on 2026-11-01.

## Maintained documentation and orchestrator note (2026-10-23)
- Resolve module roots through `walter path router` and `walter path context`; do not introduce hardcoded paths in new integrations.
- Guides: `docs/USAGE.md`, `INTEGRATION.md`, `EXECUTION.md`, `OPERATIONS.md`, `MAINTENANCE.md`, `ORCHESTRATOR.md`. Public generated references cover API/CLI, all database fields, tasks/weights, configuration and code signatures. `docs/DESIGN.md` is historical.
- `walter-router schema` returns the public tool schema. `walter-router docs --write` regenerates references from code and SQL metadata; `docs --check` fails if stale. `--offline` uses the stored schema snapshot, not a live SQL-schema verification. Export no private instance rows or secrets.
- After a source/schema change: back up, update behavior guides and API descriptions, regenerate references, run `docs --check` and appropriate tests, and update history. Module `AGENTS.md` records this maintenance rule.
- One brief producer: `walter-router brief --json` returns versioned Markdown, hash, length, source and required tools. `brief --write` publishes the Markdown and JSON to instance state and syncs supported profiles. Do not maintain another prompt copy.
- Walter Context can prepare this trusted source via `walter-context capability router --tool walter_route --tool walter_run --tool walter_decide --tool walter_plans`. Its `TurnNotes` API freezes the note for a turn and reloads on the next owner message. An actual tool inventory is required before injection is allowed.
- This source does not activate the future lot-4 general context composer, nor guarantee automatic injection in every harness. The host owns instruction placement, tool permissions, deduplication and snapshot lifetime.
- Current execution limits are explicit in EXECUTION.md: native text tool groups are limited; vision selection does not attach input; media uses a separate execution path; subprocesses run with the server's actual rights, not automatically a caller sandbox.
Validated: router suite 175 tests, context suite 43 tests, DSH port 9 tests; installed live reference check and actual Context-to-Router note loading pass. These are functional checks, not provider availability or billing evidence.



