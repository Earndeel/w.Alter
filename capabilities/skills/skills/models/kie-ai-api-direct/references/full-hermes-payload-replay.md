# Replaying a full Hermes orchestrator payload on Kie.ai

Use this when the user asks whether Opus/Kie can handle the *same orchestrator context* currently sent to another provider/model, not just a connectivity ping.

## Core distinction

A direct prompt like `Reply PONG` only validates transport. It does **not** validate continuity, memory, system prompt, skills index, or tool schemas.

A full-payload replay requires capturing the runtime request assembled by Hermes before the provider call, then adapting only the wire protocol if the source and target providers use different APIs.

## GPT-5.5 / OpenAI Responses -> Kie / Anthropic Messages

Observed source shape from GPT-5.5 orchestrator calls:

- `model`: `gpt-5.5`
- `instructions`: large Hermes system/runtime prompt
- `input`: conversation messages
- `tools`: OpenAI Responses function tools
- `tool_choice`, `parallel_tool_calls`, `reasoning`, `include`, `stream`, etc.

Kie Opus 4.8 expects Anthropic Messages format at:

`https://api.kie.ai/claude/v1/messages`

Translation required:

- `instructions` -> `system`
- `input[]` -> `messages[]` with roles `user` / `assistant`
- OpenAI function tool `{type: "function", name, description, parameters}` -> Anthropic tool `{name, description, input_schema: parameters}`
- `tool_choice: "auto"` -> `tool_choice: {"type": "auto"}`
- remove OpenAI-only fields: `reasoning`, `include`, `parallel_tool_calls`, `prompt_cache_key`, `store`, `stream`, provider timeout fields
- set target `model: claude-opus-4-8`
- set a bounded `max_tokens` for the probe

The content is still the orchestrator payload; the envelope is translated because Kie/Anthropic does not accept OpenAI Responses bodies.

## Verification checklist

1. Capture the actual runtime request immediately before the provider call.
2. Record payload size, number of messages, number of tools, and system/instructions length.
3. Replay against Kie with Bearer auth and browser-like UA.
4. Require `HTTP 200` and inspect response fields:
   - `id`
   - `model`
   - `stop_reason`
   - text preview / exact expected response
5. If the test goes through Hermes runtime, verify `state.db` billing metadata to catch silent fallback.
6. If the replay is direct HTTP, state clearly that billing metadata belongs to Kie response/provider logs, not Hermes session billing.

## Reporting language

Be precise:

- Correct: “The GPT-5.5 orchestrator payload was captured and translated to Anthropic Messages; Opus 4.8 via Kie returned HTTP 200.”
- Incorrect: “Exact payload sent unchanged” when the source was OpenAI Responses and the target is Anthropic Messages.
- Incorrect: “Continuity tested” if only a mini-prompt was sent.

## Pitfall from session 2026-06-18

A successful Kie transport ping (`KIE_RUNTIME_PATCHED_OK`) did not prove conversation continuity. The user specifically wanted the orchestrator payload, including context and tool schemas. Future tests must separate:

- transport/provider reachability;
- Hermes runtime routing/no-fallback verification;
- full-context payload replay.
