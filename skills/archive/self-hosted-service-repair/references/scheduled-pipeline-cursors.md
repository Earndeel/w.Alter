# Scheduled ingestion: cursor and delivery verification

- Align cursor predicates and ORDER BY using the same deterministic composite key, usually (created_at, id). Text/UUID IDs are not chronological counters. Resolve legacy anchors by exact tenant/bank plus ID; missing anchors must fail closed rather than silently reset.
- Test the actual SELECT with a typed WITH source AS (VALUES ...) fixture in a read-only database transaction. This exercises SQL typing/order without DDL or production writes.
- Persist an exact-ID retry after failure if the initial source query has a rolling time window; test the failed document aging out before the next invocation.
- Do not advance checkpoints, count success, or process later documents after a worker failure. Preserve successful prefixes and custom state fields. Test main return values AND an actual CLI subprocess exit status; returning 1 is useless if the footer discards it.
- Replace checkpoint files atomically only after complete serialization and file fsync. Test partial-write, fsync and replace failures; a directory-fsync failure after replace indicates uncertain durability, not an unchanged file.
- Preserve sensitivity and the stricter disclosure policy during lifecycle transitions. Unknown policy labels must fail closed; unknown graph origins should be rejected before database writes.
- Document at-least-once crash replay honestly. Backlog processing, retrospective backfill and exactly-once delivery are different acceptance criteria; do not promise them from a passing connection probe.
