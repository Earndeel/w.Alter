# Walter Memory agent facade

`walter_memory.agent_memory` owns the runtime-neutral `recall`, `retain` and `reflect` contract. MCP is only its JSON/stdin transport through `walter-memory agent-memory`.

- `recall` uses local hybrid search, cloud-allowed candidates and current canonical-owner checks. A stale index cannot loosen the owner's class; derived items require valid canonical provenance from permitted events and/or objects; missing, retracted or purged sources are excluded. It does not query the mixed legacy Hindsight bank.
- `retain` creates one classified canonical `note.recorded`, including context/tags in classification. The response explicitly says `search_projection: pending_indexer` and `cognitive_projection: not_requested`. No synchronous legacy-bank copy occurs.
- `reflect` synthesizes permitted canonical evidence through the existing Router `memory_extraction` task and the common model accounting/budget/privacy client. Its provenance and the change from Hindsight reflection are explicit. Local-only questions are refused before embedding/model access; redacted questions stay pseudonymised in cloud-facing results. Missing evidence makes no model call.

Example request, sent on stdin (never put personal content in command arguments):

```json
{"version":1,"method":"recall","caller":"codex","args":{"query":"example project","budget":"low","max_tokens":512}}
```

`budget` values are low/mid/high; recall caps its result and reflection output accordingly. Transport failures are explicit and never fall back to a less restrictive memory path. Library event/vault APIs retain local defaults for VM callers; cloud adapters impose their stricter read scope.

Tests `tests/test_agent_memory.py` simulate model calls. A live CLI read validated the real Router task and canonical search path without sending model requests or printing retrieved contents. Retention and reflection writes/model calls were not exercised against live user data.

Known scope: long-running MCP processes must be reconnected/restarted to load updated adapters. Hermes' existing Hindsight provider and voice layer are separate integrations; this facade does not claim they have been migrated. Detection/policy classification remains the source of privacy truth; it cannot retrospectively prove that all historical rows were classified perfectly.


## Curated document provenance

Curated instance documents enter the knowledge lane through canonical `document.section` occurrences. Their
availability, explicit removal, revision/idempotence rules and privacy checks are documented in
[DOCUMENTS.md](DOCUMENTS.md). An unavailable source retains its previous knowledge; returning to an older text
creates a fresh canonical occurrence when its former evidence was retracted. Historical retractions remain intact.
