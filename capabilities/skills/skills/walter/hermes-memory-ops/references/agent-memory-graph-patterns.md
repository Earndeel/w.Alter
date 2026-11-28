# Agent Memory Graph Patterns — Research Notes

Use this when evaluating external agent-memory systems (Graphiti/Zep, Letta/MemGPT, LangMem, Mem0, Cognee, LightRAG/GraphRAG, Apache AGE) for improvements to W.Alter/Hindsight. The default posture is to extract patterns, not migrate platforms.

## Baseline for W.Alter

Current W.Alter memory already has multiple layers:
- PostgreSQL/Hindsight as truth store and broad recall path.
- Qdrant as fast vector index for active/canonical memories.
- ZeRank-2 reranking.
- Async write worker for extraction.
- Dream cycle for consolidation/dedup/invalidation.
- User Model for preferences/decision signals.
- Kardex for social/contact memory.

Do not describe the system as “no graph layer”. More accurate: W.Alter has relational/entity layers, but graph traversal is not yet the primary retrieval primitive.

## External patterns worth extracting

| System | Useful pattern | W.Alter status | Actionable interpretation |
|---|---|---|---|
| Graphiti / Zep | Episodes → entities → temporal relationships → invalidation, graph-first retrieval | Partially covered | Improve temporal/provenance fields and relationship traversal in PG before adding a new graph DB |
| Letta / MemGPT | Core memory vs recall memory vs archival memory | Mostly implicit | Make context compiler budgets explicit: always-injected profile, scoped recall, deep archive |
| LangMem / LangGraph | Semantic / episodic / procedural memory taxonomy | Partially covered | Keep USER.md/User Model = semantic profile; sessions/Hindsight = episodic evidence; skills = procedural memory |
| Mem0 | Extract → evaluate → update → retrieve production loop | Mostly covered | Strengthen update/supersession checks before writing new facts |
| Cognee | Vector search as a hint, then graph triplet traversal to assemble context | Not systematic | Add optional relation-expansion after Qdrant recall for project/person/decision queries |
| LightRAG / GraphRAG | Hybrid retrieval over chunks + triplets + neighborhood summaries | Partially covered | For “explain relation/history” queries, combine PG exact rows, Qdrant candidates, and relationship neighbors |
| Apache AGE / PG graph | Cypher-like graph queries inside PostgreSQL | Not used | Consider only after plain PG graph tables + recursive CTEs prove insufficient |

## Practical recommendations for W.Alter

1. **Temporal fields everywhere**
   Normalize or add `valid_from`, `valid_to`, `supersedes`, `superseded_by`, `current`, `confidence`, and `source_episode_id` to fact/relationship records where missing. This is higher ROI than installing Graphiti.

2. **Episode provenance as first-class evidence**
   Every extracted fact/entity/relationship should point back to a raw episode/document/message. This improves auditability, contradiction handling, and user trust.

3. **PG graph traversal before new databases**
   Prefer normal PostgreSQL tables plus recursive CTEs for relationship traversal. Add Neo4j/FalkorDB/Graphiti only if PG traversal becomes a measured bottleneck or implementation drag.

4. **Intent-based context compiler**
   Before injecting memory, classify query intent: preference, person/contact, project, decision history, procedure, contradiction, exact fact, or broad semantic recall. Route to USER.md/User Model, Kardex, PG, Qdrant, skills, or combined graph traversal accordingly.

5. **Relation expansion as an add-on to vector recall**
   For queries involving “why”, “how are X and Y related”, “what changed”, “what replaced”, or multiple named entities, retrieve Qdrant candidates, then expand 1–2 hops through PG relationships and supersession links before compiling context.

## Adoption rule

Do not migrate to Graphiti just to “have graph memory”. Graphiti is useful as a checklist and possible sidecar for Kardex/decision/project dossiers, but W.Alter’s likely best ROI is a Hindsight Graph Layer inside PostgreSQL.

## Source URLs

- https://github.com/getzep/graphiti
- https://arxiv.org/abs/2501.13956
- https://www.letta.com/blog/agent-memory/
- https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- https://arxiv.org/abs/2504.19413
- https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory
- https://github.com/apache/age
