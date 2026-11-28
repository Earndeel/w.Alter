---
name: hermes-wire-context-pruning
category: devops
description: Optimize Hermes provider payloads by pruning tool outputs and reasoning blocks at send time while keeping full history in state.db.
created: 2026-06-18
updated: 2026-06-18
---

# Hermes Wire Context Pruning

Use this when Hermes sessions run continuously, context grows even with caching, or tool outputs/reasoning blocks are repeatedly reinjected into model calls.

## Core Principle

Persist everything, send only what the model still needs.

`state.db` is the audit log and retrieval source. The provider payload is a working set. Do not confuse the two.

## Preferred Architecture

1. Keep raw tool outputs, tool calls, assistant messages, and reasoning metadata persisted in session storage.
2. Before each provider call, build a sanitized message list for the wire payload without mutating persisted history.
3. Keep the stable prefix stable: system prompt, tool schemas, user profile, durable memories, loaded skill summaries, and compact session summary.
4. Minimize the volatile suffix: latest user request, the latest assistant synthesis, and only the most recent tool-call exchange needed for provider protocol validity.
5. If older details are needed, retrieve them from session storage instead of replaying every raw tool output into the model.

## What To Prune On The Wire

- Old `tool` message contents after the assistant has already synthesized them.
- Large or duplicate file reads, search results, terminal logs, browser snapshots, and skill dumps.
- Old `thinking`, `reasoning`, or `reasoning_content` blocks.
- Large tool-call arguments outside the protected recent tail.

Replace old tool results with short summaries such as:

```text
[read_file] read agent/context_compressor.py from line 820 (12,000 chars)
[terminal] ran tests -> exit 0, 47 lines output
[search_files] query matched 14 files
```

## Provider Protocol Guardrails

- Do not break assistant tool-call to tool-result ordering.
- Keep a raw recent tail intact, typically the last 8 messages, until the next assistant synthesis has consumed the latest tool exchanges.
- Some Anthropic-style, DeepSeek/Kimi/Moonshot, or MiMo thinking endpoints require `reasoning_content` echo-back for assistant tool-call messages. For old assistant tool-call messages, a minimal pad such as `reasoning_content: " "` can satisfy validation without replaying chain-of-thought.
- Preserve `tool_call_id`, tool-call ordering fields, and role sequence even when replacing old tool `content` with a placeholder.
- Never delete persisted history just to reduce prompt payload; use a wire-only copy.

## Implementation Pattern

Best hook: the central API kwargs builder, before transport-specific conversion, so all provider paths receive the same trimmed working set. In Hermes Agent this is typically `agent/chat_completion_helpers.py::build_api_kwargs()`.

Recommended shape:

1. Deep-copy `api_messages`.
2. Compute `prune_before = len(messages) - keep_tail` with `keep_tail` configurable, e.g. `HERMES_WIRE_PRUNE_KEEP_TAIL=8`.
3. For messages older than the tail:
   - `role == "tool"`: replace `content` with a short placeholder, preserve `tool_call_id`.
   - `role == "assistant"`: strip inline `<think>` text and remove `reasoning`, `reasoning_content`, `reasoning_details`, `codex_reasoning_items`, encrypted reasoning fields.
   - if old assistant message has `tool_calls` and the active provider requires thinking echo-back, set `reasoning_content` to a single space.
4. Expose `HERMES_WIRE_PRUNE=0` as a regression-debug escape hatch.

See `references/wire-pruning-cache-strategy.md` for the session-specific checklist.

## Cache Strategy

Cache works best when the prefix is stable and the changing suffix is small.

Prioritize cache-write for:
- system and developer instructions;
- tool schema blocks;
- stable user/memory context;
- compact conversation summaries.

Avoid cache-writing churn from:
- raw tool outputs;
- browser snapshots;
- repeated file dumps;
- thinking/reasoning blocks;
- session-specific transient logs.

A high cache-read rate does not save a bloated volatile tail. Measure the percentage of total prompt tokens occupied by the tail before optimizing smaller static blocks.

## Verification Checklist

1. Compare total provider payload tokens before and after wire pruning.
2. Separately estimate stable prefix tokens and volatile suffix tokens.
3. Confirm cache read/write counters improve on repeated turns.
4. Confirm tool-call protocol validity with at least one tool-use turn.
5. Confirm older details remain recoverable from session storage.

## Compression Threshold Companion

Current Hermes live compression uses `agent.context_compressor.calculate_compression_threshold_tokens()`:

- GPT-5.5-family models: threshold equals the full context window, so normal live compression is effectively disabled.
- Other models: threshold is `min(100_000, context_length * threshold_percent, context_length)`, floored by `MINIMUM_CONTEXT_LENGTH`.
- If the auxiliary summary model has a smaller usable context, `_effective_max_threshold` caps the trigger and survives model/context refreshes.
- Gateway session hygiene must call the same helper, not recompute `context_length * pct` independently.

This is separate from wire pruning: compression mutates the live session history into summaries, while wire pruning only mutates the provider-request copy and must never alter `state.db`.

## Related Existing Skill

`hermes-context-management` covers broader compression diagnostics, but it may be blocked by skill security scanning because it documents prompt/persistence/audit commands. If it is editable, prefer merging this pattern there; if blocked, keep this skill as the safe companion skill.
