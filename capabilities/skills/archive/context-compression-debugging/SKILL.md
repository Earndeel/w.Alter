---
name: context-compression-debugging
category: devops
description: Debug ContextCompressor IndexError and boundary conditions — reproduction, fix, and payload measurement. Extends hermes-context-management with hard-won bug patterns.
created: 2026-07-13
---

# Context Compression Debugging — Boundary Bugs & Payload Measurement

Use when diagnosing compression failures, IndexError crashes in `context_compressor.py`, or measuring which roles dominate context payload in `state.db`.

For threshold-loop diagnosis, runtime/config/source separation, activation status, and the all-tool boundary reproducer, read `references/threshold-loops-and-boundary-overruns.md`.

## Pipeline: compress() call chain

```
compress() [L.2707]
 ├─ Phase 1: _prune_old_tool_results()      [L.2767]
 ├─ Phase 2: Boundaries
 │   ├─ _protect_head_size()                 [L.2775]
 │   ├─ _align_boundary_forward()            [L.2776]
 │   └─ _find_tail_cut_by_tokens()           [L.2779]
 │       ├─ _align_boundary_backward()        [L.2577]
 │       ├─ _ensure_last_user_message_in_tail [L.2677]
 │       │   └─ _find_turn_pair_end()         [L.2554]
 │       └─ _ensure_last_assistant_message_in_tail [L.2684]
 ├─ Phase 3: _find_latest_context_summary()  [L.2808]
 ├─ Phase 4: _generate_summary()
 ├─ Phase 5: _build_compressed_messages()
 └─ Phase 6: _sanitize_tool_pairs()          [L.2947]
```

## Three-Layer Data Lifecycle

| Layer | Implementation | Mutated by compress? | Role |
|-------|---------------|---------------------|------|
| **Ledger** | `state.db` messages table (`active=1`, `compacted=0`) | **Never** | Source of truth |
| **Transcript** | `agent.messages` (Python list in RAM) | **Yes** — `_prune_old_tool_results()`, `compress()` | Working copy |
| **Prompt view** | `api_messages` in `conversation_loop.py` L.787-900 | **Yes** — slimmed via `_sanitize_api_messages()`, `_drop_thinking_only_and_merge_users()` | What the provider receives |

## ⚠️ Pitfall: IndexError — `compress_end > len(messages)`

### Symptom
`IndexError: list index out of range` at `context_compressor.py:2808` — `_find_latest_context_summary(messages, 1, end=...)` where `end > len(messages)`.

### Root cause
`_find_tail_cut_by_tokens()` line 2686: `return max(cut_idx, head_end + 1)`.
When `compress_start` reaches `len(messages)` (all post-head messages are `role=tool`), `head_end + 1 = len + 1`, exceeds bounds. The guard at L.2781 (`compress_start >= compress_end`) does NOT fire because `len < len + 1`.

### Trigger
All messages from `_protect_head_size()` onward are `role=tool`. Can happen after a prior compression where tool results survive but their assistant tool_calls were pruned, or in degenerate all-tool sessions.

### Fix (one-line, line 2686)
```python
# Before (bug):
return max(cut_idx, head_end + 1)

# After (fix):
return min(max(cut_idx, head_end + 1), len(messages))
```

### Verification
RED test at `tests/agent/test_tail_cut_overrun_index_error.py` (two tests: unit-level boundary check + e2e compress() call). See `references/indexerror-reproduction.md` for the exact crash trace.

## Payload Composition Measurement

Use the script in `references/payload-composition-measurement.py` to measure per-role composition from `state.db`.

Typical real-world findings:
| Role | % of total chars |
|------|-----------------|
| `tool` | 72–97% |
| `assistant` | 3–10% |
| `user` | <1% |

Tool-result content often dominates long transcripts, but do not assume it. Measure both layers:

1. persisted message-role content in `state.db`; and
2. fixed wire overhead (`instructions` plus serialized tool schemas), which can dominate short or freshly compacted turns.

Choose prompt-view tool-result slimming only when the first layer is actually dominant. When tool schemas or the skills catalog dominate the wire payload, use lazy tool routing or selective skill injection instead; see `hermes-prompt-payload-slimming`.

## Pitfalls

- Never mutate `state.db` rows to save tokens — only the prompt view should be slimmed.
- When `token_count` is NULL in `state.db` (common for older sessions), boundary calculations rely on rough char-based estimates which are less precise.
- Tool results of 57k+ chars (HTML pages, full log dumps) dominate payload — a single such message can consume the entire tail budget.
