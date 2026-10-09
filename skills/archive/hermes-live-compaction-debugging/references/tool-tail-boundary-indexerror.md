# Tool-tail boundary IndexError

## Trigger

Automatic live compaction can fail when the transcript ends with an assistant tool-call message followed only by one or more `role=tool` results, and the protected-head boundary lands inside that final tool block. Large parallel reads can cross the context threshold in exactly this shape before a normal assistant reply closes the turn.

## Root cause

`compress()` computes the protected-head boundary and `_align_boundary_forward()` advances it past consecutive tool results. When those results occupy the remainder of the transcript, `compress_start` becomes `len(messages)`.

`_find_tail_cut_by_tokens(messages, compress_start)` can then enforce `head_end + 1` without clamping it to `len(messages)`, yielding `compress_end == len(messages) + 1`. The ordinary `compress_start >= compress_end` guard does not fire, and `_find_latest_context_summary()` indexes beyond the list.

This is a local compressor boundary defect. The next LLM request has not yet been sent.

## Reproduction recipe

1. Read the failed session's rows from `state.db` up to the crash timestamp.
2. Rebuild each message with `role`, `content`, `tool_calls`, `tool_call_id`, and tool name; preserve ordering.
3. Instantiate `ContextCompressor` with the live model, provider, context length, `protect_first_n`, `protect_last_n`, threshold, and target ratio.
4. Stub `_generate_summary`; the crash occurs before summary generation.
5. Replay `compress()` and instrument:
   - `_protect_head_size`
   - `_align_boundary_forward`
   - `_find_tail_cut_by_tokens`
   - `_find_latest_context_summary`
6. Confirm `compress_start == len(messages)` and `compress_end == len(messages) + 1`.

A minimal role-only fixture can reproduce the index failure, but the persisted transcript is the authoritative fixture because omitted tool-call IDs may introduce unrelated sanitizer behavior.

## Fix invariants

Apply both semantic and defensive protections:

- if forward alignment yields `compress_start >= len(messages)`, return the original transcript unchanged;
- clamp all tail-cut results to `len(messages)`;
- clamp summary-scan bounds and return no match when `start >= end`.

The semantic rule is primary: protected head plus a trailing tool group contains no compressible middle window.

## Regression matrix

1. User → assistant with multiple matching tool calls → all matching tool results, boundary inside the tool block.
2. Same shape with enough tool output to trigger automatic preflight compression.
3. Same shape followed by a normal user/assistant turn, proving valid compaction still occurs.
4. Mismatched/orphaned tool IDs, proving pair sanitization remains independent.
5. `protect_first_n` below, equal to, and above the transcript length.

For the first two cases, assert: original messages returned, summary model not called, and no `IndexError`. For the third, assert that compaction occurs and tool groups remain intact.
