# OpenRouter model + reasoning contract — Scena reference

## Why this exists

A user correction required Scena’s conversational/executor brain to be GPT-5.6 Luna through OpenRouter at maximum thinking. The runtime already selected Luna but still sent `reasoning.effort = high`; prompts, tests, and a Telegram status message repeated that stale level.

## Provider facts verified live

Catalog endpoint: `https://openrouter.ai/api/v1/models`

Verified model:

- ID: `openai/gpt-5.6-luna`
- Name: `OpenAI: GPT-5.6 Luna`
- Relevant supported parameters: `reasoning`, `reasoning_effort`, `tools`, `tool_choice`, `include_reasoning`, `max_completion_tokens`

OpenRouter reasoning documentation states that `xhigh` uses the same maximum allocation as `max` (approximately 95% of the output-token budget). Scena normalized “max thinking” to the explicit OpenAI-style value `xhigh`.

Authoritative pages:

- `https://openrouter.ai/docs/guides/best-practices/reasoning-tokens`
- `https://openrouter.ai/docs/api_reference/parameters`

Re-query the live catalog and current docs before reusing these values; model contracts evolve.

## Scena routing contract

- Conversation, intake, orchestration, tool calling, and post-STT dialogue: `openai/gpt-5.6-luna` via OpenRouter, `reasoning.effort = xhigh`.
- Planning after a complete brief: GPT-5.6 Sol via OpenRouter, also `xhigh`.
- Audio transcription: Gemini specialist only; its transcript rejoins Luna for dialogue.

## Implementation pattern

1. Define shared model and maximum-effort constants in the OpenRouter client.
2. Spread the caller payload first, then overwrite `model` and `reasoning` in the wrapper. This prevents route-local downgrades.
3. Reuse the constants in system prompts, guided-intake prompts, admin model configuration, and status output.
4. Expose `provider=openrouter` and `reasoning_effort=xhigh` in diagnostics so production routing is observable.
5. Test the actual outbound OpenRouter URL, model, reasoning object, tools, and authorization shape.

## Regression lesson

Several tests identified planner traffic using `payload.reasoning.effort === 'xhigh'`. That worked only while Luna used `high`; moving Luna to maximum reasoning made executor calls look like planner calls. Classify roles by `payload.model`, then independently assert that each role has the required reasoning effort.

Cover at least:

- direct conversational/tool turns;
- structured/guided intake analysis;
- voice transcription followed by natural dialogue;
- admin model-config output;
- prompts and status text for stale labels;
- Worker bundle/dry-run after the source change.
