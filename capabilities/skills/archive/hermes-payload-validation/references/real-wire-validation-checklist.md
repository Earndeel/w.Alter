# Real-wire payload validation checklist

Use this reference for production validation of context slimming. It records the evidence boundary that matters: what Hermes attempted to send, what the provider accepted, and what remains only in the persistent ledger.

## 1. Prepare a controlled run

1. Record the active session ID, model, provider, API mode, context window, output reservation, and the raw tool-row hashes/lengths in `state.db`.
2. Enable `HERMES_DUMP_REQUESTS=1` or the equivalent configuration dump for one controlled run only.
3. If prompt, memory, skill-index, or compression code/config changed, use a fresh session or explicit prompt reset. A resumed session can reuse a stored `system_prompt` and make a correct change appear absent.
4. Keep the run's model/provider fixed. A session resumed under a different route is not an A/B comparison.

## 2. Classify the evidence

- **wire_attempted**: a sanitized request dump exists after Hermes request assembly/middleware.
- **provider_accepted**: the request returned a usable provider response.
- **actual_usage_available**: the accepted response contains provider input/cache/output usage.

Never collapse these into one status. A provider HTTP 200 with an empty stream, server exception, or exhausted retries is `wire_attempted=true`, `provider_accepted=false`, `actual_usage_available=false`.

## 3. Normalize the payload

Measure the final dump, not `state.db`:

- Chat Completions: `messages`, `role=tool`, assistant `tool_calls`.
- Responses/Codex: `input`, `function_call`, `function_call_output`, `instructions`.
- Anthropic Messages: `system` can be a string or list of blocks; `tool_use` and `tool_result` are embedded in `message.content`.
- Bedrock/native transports: normalize the adapter's final assembled dict before comparing roles.

Count diagnostic subcategories (skills, Hindsight, summary, USER/MEMORY) as overlays; do not add them again to the total payload token count.

## 4. Acceptance checks

For every real dump, record:

- total estimated tokens, model limit, output reserve, headroom;
- system/permanent text and tool-schema tokens;
- skill index, full skill bodies, USER.md, MEMORY.md, SOUL, Hindsight, summary, recent conversation, tool calls/results, current user turn;
- top ten payload elements;
- raw tool results over 4,000 characters still on wire;
- full `SKILL.md` bodies and duplicate `skill_view` loads;
- digest count and `state_ref` count;
- provider acceptance and tool-call pairing;
- raw ledger hashes before/after.

The tool working-set cap is an active-payload invariant only. Raw output must remain unchanged in `state.db` and be recoverable through the `state_ref`/exact-recall path.

## 5. Stability protocol

Capture A, add a comparable batch of new tool calls/results, capture B, then repeat for C. Compare the same model/provider and the same task shape. A/B/C retries of one failed request are **not** a stability test; they only show retry determinism.

## 6. Close the run

Turn full dumps off, retain the compact report and the evidence summary, and rerun the targeted payload/ledger tests. If the provider never accepts the request, report the exact blocker rather than inventing cache or actual-token numbers.
