---
name: hermes-context-compression
category: devops
description: Configure, audit, and verify Hermes live context compression so long sessions keep a compact timestamped history plus a clean recent tail.
created: 2026-06-25
updated: 2026-06-25
---

# Hermes Live Context Compression

Use this when Monsieur asks to inspect, tune, or repair Hermes context compression, especially around long sessions, cached-token accounting, auxiliary summarizers, and what survives compaction.

## Target architecture

1. **Compression trigger uses real prompt footprint + prompt budget soft caps**
   - Count cached input tokens as part of the live context size.
   - Include provider fields such as cache-read tokens, cache-write tokens, and OpenAI-style cached-token details when updating compressor usage.
   - Enforce `compression.history_soft_cap_tokens` (default 32,000) on the dynamic transcript alone, so long-context models do not replay stale history merely because the hard provider threshold has not been reached.
   - Enforce `compression.target_total_prompt_tokens` (default 50,000) as a soft full-payload budget for routine turns. This target also shrinks automatic context-file injection and can demote the skills index to names-only while full skill text remains available through `skill_view`.
   - If cached tokens are ignored, a huge cached prompt can look tiny and compression will not fire. Très pratique, si the goal is to slowly drown.

2. **Cheap auxiliary summarizer**
   - Prefer `auxiliary.compression.provider: gemini` with `model: gemini-3.1-flash-lite` when the free AI Studio key is available.
   - Verify with a real compression-task LLM call, not config inspection alone.
   - If the configured auxiliary model fails, surface that clearly; silent fallback hides the broken setup.

3. **Layered transcript after compaction**
   - Keep the most recent conversational surface raw, normally the last 10 messages.
   - Strip assistant thinking/reasoning fields from that raw tail.
   - Keep tool-result messages structurally present when paired with assistant tool calls, but replace bulky result payloads with compact tool summaries plus `state_db://...` anchors.
   - Store older relevant work in structured compaction summaries: `delta_summary`, `compact_summary`, `session_summary`, `tool_evidence`, and `state_anchors`.
   - Rebase delta summaries periodically so they do not accumulate indefinitely; the compact summary becomes the operational memory while state.db remains the exact recall source.

4. **Timestamped historical blocks**
   - Serialize compacted source turns with timestamps in `YYYYMMDDHHMMSS+07` by default for this profile, keeping the source timezone offset when known.
   - Preserve timestamps on concrete actions, events, blockers, decisions, resolved questions, state changes, and state.db anchors in the summary.
   - Do not place dynamic timestamps in the static prefix; summaries and anchors are dynamic/semi-static blocks.
   - This prevents resumed agents from treating old completed work as fresh instructions.

## Implementation checkpoints

- Main code path: live session compression in `agent/context_compressor.py`.
- Feasibility wiring: auxiliary compression provider/model resolution and context-length checks.
- Session-level compaction may rewrite the live message list while preserving enough recent context to continue.
- Keep provider message alternation valid after pruning; do not remove paired tool-result messages blindly.

## Reference material

- `references/layered-compaction-tail.md` — session detail for cached-token triggering, Gemini free-tier probe, clean raw tail, and timestamped summary blocks.

## Verification checklist

1. Run syntax verification on the modified compression files.
2. Run targeted tests around context compression and compression feasibility.
3. Capture a before/after payload with a short raw tail and a long mocked conversation; measure total chars/tokens, static prefix, semi-static block, compact summary/deltas, raw tail, tools, and skills.
4. Verify a mocked large tool result: payload contains only a summary + `state_db://...` pointer, while exact raw output is recoverable from state.db by `tool_call_id`.
5. Verify delta reassembly: after the threshold, old `delta_summary` entries are rebased instead of growing forever.
6. Verify the auxiliary compression route with a small `call_llm(task="compression", ...)` request and confirm the expected model responds.
7. Run the Hermes config checker.
8. Inspect the scheduled jobs list if the task involved removing or replacing a cron-driven watchdog.

## Pitfalls

- Use `python3` in lean Linux environments; do not turn `python` absence into a durable rule.
- Config presence is not proof that the free-tier Gemini route works; only a real auxiliary call proves it.
- Increasing the protected recent-tail floor changes exact boundary tests; update assertions that pin the first preserved message.
- Tool payload pruning should preserve continuity and provider validity, not merely delete context.
