# Context acceptance — 2026-10-18, extended 2026-10-21 (lot 2)

The corpus is synthetic, versioned (`synthetic-retention-v1`), and uses no user
history, credentials, network or model calls. Its 14 cases cover ordinary tools,
a constraint in the middle of a long user message, French/Japanese/Arabic text,
a superseding decision, consecutive user messages, 36 tool refs, normalized
attachment refs, middle and intermediate assistant explanations, oversized user
and assistant text, a small host budget and system/developer updates.

All visible dialogue and refs must remain present after a second checkpoint;
no input may be mutated. The two assistant questions have fixed supported answers:
“Why was migration postponed?” → replica lag exceeded 42 seconds; “Why was the
deployment stopped?” → checksum differed from the signed manifest. These tests
check that answer evidence remains visible, not that a model will answer correctly.
Thresholds were declared before execution; no model judging or threshold tuning.

Corpus SHA-256: `dfcadc1af3404eb5cd2538d8e0dc6a9fc9fec971136e68e1b7d538b1338ed989`.

| Same 14-case corpus | Prior checkpoint | Full dialogue checkpoint |
|---|---:|---:|
| Failed cases | 2 assistant details | 0 |
| Safe expected refusals | 5 | 5 |
| Accepted input estimate | 335,910 | 335,910 |
| Output estimate | 7,123 | 9,532 |
| Reduction | 97.88% | 97.16% |
| Renderer p95, one local run | 1.097 ms | 1.098 ms |

Timing is a single local observation, not a service latency SLO. Counts use the
core character-based estimator, not a provider tokenizer. Large synthetic tool
outputs intentionally exercise the useful compression case; prose-heavy histories
can save little or refuse. Repeated checkpoints grow until their dialogue no
longer fits the record budget, at which point refusal preserves the host surface.

27 Python tests cover core and public Hermes adapter behavior. Nine Node tests
exercise the actual DSH 0.2.0-rc.2 Session, CompactionEngine and ToolRuntime with
fixture provider metadata: real transactions, repeated compactions, replay, paged
source recovery, budget/error/role guards, abort and concurrent lock handling.
The DSH port refuses privileged roles anywhere inside the span, including its
first node; only the injected durable global system head is exempt.

Remaining limits: no semantic model-answer evaluation, no live provider cache or
token accounting, no full multimodal understanding, clipped action arguments,
tool payload retrieval required. The lossy Hermes projection is a different mode
and remains inactive; this corpus does not qualify it. Codex/Claude compaction
remains native. Run `walter-context acceptance` to reproduce the deterministic gate.

## Lot 2 (2026-10-21): one record for both host contracts

The checkpoint and the projection now render the same record (`layers.dialogue`). The gate gains
`projection_user_text_visibility` = 1.0, checked on every accepted case at both projection levels:
- *full*: the owner's text is verbatim;
- *one line*: the owner's text is whole, with whitespace folded.

Same corpus (same SHA-256), same thresholds otherwise:

| Same 14-case corpus | Lot 0 | Lot 2 |
|---|---:|---:|
| Failed cases | 0 | 0 |
| Safe expected refusals | 5 | 5 |
| Checkpoint output estimate | 9,532 | 7,882 (status folded into each action line) |
| Projection owner text visible | not gated (legacy record clipped at 1,200 chars) | 100%, both levels |

Real-history replay, same 21 A8 chains (1,137 calls): 58.4k → 59.6k tokens per call (+2%), uncached 3,358 → 3,375,
cost 0.648 → 0.657 of the uncompressed history. Hermes real: 72.2k, 4,631, 0.717.
