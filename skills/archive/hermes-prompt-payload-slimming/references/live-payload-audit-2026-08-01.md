# Live W.Alter payload audit — 2026-08-01

Session-specific baseline for validating prompt-view slimming on a real Hermes Desktop session. Re-measure before treating any value as current.

## Measurement method

1. Build a fresh `AIAgent` with the live profile, platform, provider, model, and session ID, but do not make a provider call.
2. Measure the three prompt tiers with `build_system_prompt_parts(agent)`:
   - `stable`: cross-session/cacheable instructions;
   - `context`: workspace and project context;
   - `volatile`: memory, user profile, timestamp, provider/platform metadata.
3. Measure the exact serialized tool schema returned by `get_tool_definitions()` and record both schema count and serialized characters.
4. Load active history from `SessionDB`, render a copy through `slim_prompt_history()`, and compare raw versus rendered characters overall and by role.
5. Report characters and tokenizer counts separately. If the provider tokenizer is unavailable, label `characters / 4` as an estimate, never as exact billing.
6. Distinguish transmitted input, cacheable prefix, cache-hit billing, and output tokens. They are different cost surfaces.

## Verified baseline

| Layer | Characters | Estimated tokens (`chars / 4`) |
|---|---:|---:|
| Stable system prompt | 46,282 | 11,570 |
| Workspace context | 1,479 | 370 |
| Volatile prompt | 2,956 | 739 |
| 34 tool schemas | 62,608 | 15,652 |
| Fixed subtotal | 113,325 | 28,331 |

Active history at measurement time:

- 136 messages;
- raw history: 371,367 characters, approximately 92,842 tokens;
- slim prompt view: 65,921 characters, approximately 16,480 tokens;
- reduction: 305,446 characters / approximately 76,362 tokens / 82.2%;
- estimated next input before fresh memory prefetch: 44,811 tokens instead of 121,173.

The largest remaining fixed cost was the tool schema surface, not historical tool output.

## Behavioral verification completed

- The first pending `skill_view` result remains raw so the model actually reads the skill.
- Consumed large tool results become deterministic digests.
- Repeated skill loads can become `[SKILL ALREADY LOADED]` immediately.
- Digests are byte-idempotent across later prompt builds.
- Raw tool content remains in `state.db` and exact `state_ref` recall returned byte-identical content (verified by SHA-256).
- Provider-message tool-call pairing remains valid after rendering.

## Audit pitfalls

- Do not infer the active model from `config.yaml` alone; a resumed Desktop session can be pinned to another model. Read session metadata too.
- Do not infer live gateway/platform state from config alone; query the runtime status surface.
- Do not mutate the raw conversation ledger to save prompt tokens. Slim only the provider-facing copy.
- Do not add timestamps or changing metadata to digests; that defeats prompt-cache prefix stability.
- Do not claim invoice savings directly from token reduction when provider cache pricing or subscription credits are opaque.
