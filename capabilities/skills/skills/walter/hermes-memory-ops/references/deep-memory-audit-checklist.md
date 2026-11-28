# Deep Memory-System Audit Checklist

Use this reference for read-only audits of a layered Hermes memory stack. It is intentionally architecture-level: adapt service names and ports to the live installation.

## 1. Map the actual data path

Trace definitions and usages before accepting architecture documents as reality:

1. Always-injected files: identity, user profile, critical micro-memory.
2. Session store: transcript, FTS indexes, compression markers, session lifecycle.
3. External provider: initialization, `prefetch`, `sync_turn`, session-boundary flush, shutdown.
4. Truth store: raw observations versus canonical facts, status transitions and provenance.
5. Derived indexes: vector store, graph, reranker and outbox worker.
6. Procedural memory: skills and their loading path.
7. Experimental gateways/services: verify that Hermes actually calls them.

A running service is not necessarily on the production request path. Search callers, unit files and live listeners.

## 2. Separate liveness, freshness and correctness

A healthy HTTP endpoint proves only liveness. Add functional checks:

- age of newest raw observation;
- age of newest canonical fact;
- last successful profile compilation and consolidation;
- active timers whose last oneshot service result is failed;
- outbox pending/error/retry counts;
- vector-sync status distribution;
- last successful session-boundary flush.

Flag a pipeline as degraded when ingestion advances but a downstream layer's newest record does not.

## 3. Verify runtime isolation

For each systemd service, compare:

- `ExecStart` interpreter;
- dependency availability in that exact interpreter;
- `EnvironmentFile` and working directory;
- service/timer result and recent dedicated log;
- whether the service depends on a Hermes-managed venv that may be replaced during upgrades.

Prefer a dedicated, pinned venv for custom memory services. Capture the repair procedure, not a transient missing-package claim.

## 4. Reconcile like with like

Before reporting PG↔vector drift, identify the precise indexed relation and ID mapping.

- If the vector worker indexes canonical facts, compare vector points with eligible canonical facts.
- Do not compare raw observations with a canonical-fact index.
- Validate deleted, superseded, expired and historical policies separately.
- Check whether rows marked `error` still have vector points; status labels alone are not evidence.
- Confirm that health and reconciliation scripts implement the same contract as the sync worker.

A large count ratio can be correct stratification rather than drift.

## 5. Audit retrieval quality with policy probes

Use several known, non-sensitive critical rules as probes. For each retrieval path record:

- rank of the expected fact;
- number of returned items;
- irrelevant or contradictory results;
- total latency and stage breakdown (embedding, search, reranking, graph);
- whether current policy comes from always-injected profile memory or semantic recall.

Never print private memory text in the report; report ranks, counts and categories. Critical safety/preferences must remain in deterministic profile or micro-memory, not depend solely on semantic retrieval.

## 6. Check prompt-cache-safe recall wiring

Trace when the query is known, when prefetch starts, when its result is consumed, and when the system prompt is cached.

Warning pattern: prefetch is queued after a response while provider context is only read during a once-per-session system-prompt build. That can make automatic recall stale, one turn late or effectively unused.

Preferred design: prefetch for the current query before the LLM call and attach bounded memory context to the current user turn without rebuilding the stable system prefix or creating an extra synthetic user message.

## 7. Inspect data quality and graph cost

Aggregate without exposing content:

- counts by type/status/scope/privacy;
- exact duplicate groups and excess rows;
- freshness windows;
- embedding and sync coverage;
- usage/last-used coverage;
- graph links per unit, self-links, duplicate edges and relation sizes;
- active versus historical ratios.

Measure retrieval gain before retaining an expensive graph layer. Self-links, duplicate edges and unbounded semantic degree are cleanup candidates.

## 8. Audit storage and retention

Measure:

- session DB size, message/session counts and FTS latency;
- payload bytes versus total DB size to estimate index overhead;
- old open sessions and sessions over the hygiene message limit;
- PostgreSQL/Qdrant volumes;
- logs, snapshots and backups by age/count/size;
- effective retention, not merely configured retention.

Repeated full database snapshots for tiny maintenance actions are a poor cost/benefit trade. Keep bounded recent recovery points unless policy requires more.

## 9. Security boundary

For every listener, verify bind address and route capabilities:

- bind read/write memory services to localhost or an explicitly intended private interface;
- authenticate mutation routes;
- distinguish an action-policy firewall from network authentication;
- inspect CORS separately;
- never infer Internet exposure solely from a wildcard listener—also state what upstream firewall was or was not verified.

## 10. Report priorities

Use this order:

1. Broken learning or data-loss path.
2. Unauthenticated mutation/excessive network exposure.
3. False-green monitoring and invalid reconciliation contracts.
4. Retrieval correctness and cache-safe integration.
5. Storage/retention and graph efficiency.
6. Optional architectural consolidation.

Lead with measured impact and cost/benefit. Do not recommend replacing a working layer merely because a parallel architecture exists.