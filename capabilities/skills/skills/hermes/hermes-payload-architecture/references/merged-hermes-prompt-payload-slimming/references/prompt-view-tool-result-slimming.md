# Prompt-view tool result slimming implementation recipe

This reference captures the reusable debugging/implementation pattern from a Hermes payload-cost optimization session.

## Symptom

A prompt audit shows total tokens dominated by `role=tool` messages even after memory cleanup and compaction improvements. Example proportions seen in the field: around 120k prompt tokens, with roughly two thirds from tool results. Common culprits are `skill_view`, `execute_code`, `terminal`, `search_files`, and large JSON outputs.

## Diagnosis checklist

Measure before changing code:

- total estimated tokens
- chars/tokens by role
- top 10 largest messages
- top tool results by size and tool name
- repeated full `skill_view` count
- existing digest/reference count

If tool role is above 20%, optimize render-layer history before changing memory files.

## Three-Layer Data Lifecycle

Understanding the separation is critical for choosing the right slimming point:

| Layer | Where | Mutated? | Slimming safe? |
|-------|-------|----------|---------------|
| **Ledger** | `state.db` messages table | Never | ❌ Never mutate raw rows |
| **Transcript** | `agent.messages` (RAM) | Yes, by `compress()` | ⚠️ Compression-only |
| **Prompt view** | `api_messages` before provider call | Yes, every turn | ✅ This is the slimming point |

The rule: slim only `api_messages` before the provider call. Never touch `state.db` for token savings. After `compress()` reshapes the transcript, slimming runs on the `api_messages` copy — ledger stays intact for audit and recall.

## Payload Composition Baseline

Real-world measurements from live sessions (see `context-compression-debugging` skill for measurement script):

| Role | Typical % of total chars |
|------|--------------------------|
| `tool` | 72–97% |
| `assistant` | 3–10% |
| `user` | <1% |

This confirms tool-output slimming is the single highest-impact optimization. If `tool` role is above 20% of provider payload, optimize the render-layer history before changing memory files.

## Implementation checklist

1. Locate provider-call assembly, not just compaction.
2. Insert prompt-view slimming immediately before provider conversion/caching.
3. Build a copied message list; do not mutate the live/source history.
4. Map assistant tool call IDs to tool names so digests know which tool produced each `role=tool` result.
5. For each tool result:
   - small: keep inline
   - consumed and large: replace with digest
   - pending and medium: keep once
   - pending and huge: digest + excerpt
6. Add skill registry for `skill_view`:
   - first load: digest long content
   - repeated load: `[SKILL ALREADY LOADED]` with version hash and reference
7. Add second pass if tool role still exceeds budget.
8. Store metrics for the last slimming pass on the agent/session.

## Digest shape

```text
[TOOL RESULT DIGEST]
tool: skill_view
tool_call_id: call_x
timestamp: YYYYMMDDHHMMSS+07
status: success
summary: "Loaded skill ...; full content available via recall reference."
key_points:
- "..."
paths:
- /path/if/relevant
state_ref: state_db://session:{session}/message:{message}/tool_call:{tool_call}
raw_available_in_state_db: true
```

When under severe role budget pressure, a one-line digest is acceptable if it still preserves a recall reference and `raw_available_in_state_db: true`.

## Required tests

- source transcript remains raw after slimming
- large historical tool output absent from prompt view
- digest includes recall reference
- repeated skill_view does not re-add full content
- inline-once behavior for pending medium result
- huge pending result uses digest + excerpt
- role=tool budget enforced under load
- static prefix is unchanged and free of dynamic metadata

## Example measurement result

A representative synthetic payload:

- Before: 52,845 estimated tokens
- After: 12,273 estimated tokens
- Tool role: 70.7% to 6.6%
- Tool chars: 149,530 to 3,242
- Digests: 8
- Recall references: 8
- Duplicate skill_view slimmed: 2

Use these numbers only as a sanity check; the invariant is raw preservation plus large prompt reduction.
