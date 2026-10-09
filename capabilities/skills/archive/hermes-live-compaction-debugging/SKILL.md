---
name: hermes-live-compaction-debugging
description: Diagnose and repair Hermes Agent live conversation compaction failures, including boundary errors, tool-call grouping, summary-model failures, and pre-API compression crashes. Use when a run aborts during context compression or the next provider request is never sent.
---

# Hermes Live Compaction Debugging

## Scope

This skill covers `agent/context_compressor.py` and the live path through `conversation_loop` / `conversation_compression`. It does not cover offline trajectory compression or generic prompt-size optimization.

## Diagnostic order

1. Read the full gateway crash traceback; do not infer the failure from the final UI string.
2. Decide whether the exception occurred before, during, or after the summary-model request.
3. Reconstruct the exact pre-crash transcript from `state.db`, preserving roles, `tool_calls`, `tool_call_id`, reasoning fields, and order.
4. Replay the boundary calculation with the live compression configuration while stubbing summary generation if the crash occurs before the LLM call.
5. Inspect provider/base URL only when the traceback proves the summary request was actually attempted.
6. Add a regression fixture matching the real role/tool-pair shape before patching.

## Boundary invariants

Every compaction implementation must preserve these invariants:

- `0 <= compress_start <= len(messages)`
- `0 <= compress_end <= len(messages)`
- summary scans run only when `compress_start < compress_end`
- an assistant tool-call and its matching tool results remain on the same side of a boundary
- a transcript with no compressible middle window returns unchanged without invoking the summary model

Clamp defensively at scanners, but also fix the earlier semantic calculation that produced the invalid boundary.

## Tool-result tail failures

A high-risk shape is a turn ending in one assistant tool-call message followed only by tool results. Forward alignment can advance the start boundary to the end of the list. Tail-cut code must not then manufacture `head_end + 1` beyond that end.

For the reproduction, root cause, and regression matrix, see `references/tool-tail-boundary-indexerror.md`.

## Distinguish compressor bugs from provider bugs

- Traceback in boundary or message-scanning code before `_generate_summary`: local compressor defect.
- HTTP/auth/timeout error inside `_generate_summary`: summary provider or transport issue.
- Successful summary followed by malformed tool pairs: post-compression sanitizer/repair issue.
- No next main-model billing entry after a local compressor exception: expected; the provider call was never reached.

Do not debug the main model, credentials, or edge protection until the execution path proves a request crossed that boundary. Provider blame is fashionable; stack traces remain less theatrical and more useful.

## Verification

A fix is complete only when:

1. the exact persisted transcript replays without exception;
2. the no-middle-window case performs no summary call;
3. a nearby valid transcript still compacts;
4. matching and orphaned tool-pair tests pass;
5. one real gateway turn crosses the previous trigger and reaches the next model call.

## Pitfalls

- Replaying only message roles can create artificial orphan-tool behavior; preserve IDs and tool-call payloads.
- A UI error string is not the root cause; use the crash log traceback.
- Restarting a long-lived gateway just to test source edits can terminate unrelated children in the same service cgroup; inspect process ownership first.
- Do not persist a transient provider outage as a permanent skill rule. Capture retry/verification technique instead.
