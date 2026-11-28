# Client-facing response style contract — Scena example

## Failure signal

Client-facing Telegram replies were judged too verbose and too formal even though the prompt already said “professional, accessible” and “max 3–4 sentences.” Those adjectives were not measurable enough and encouraged consultant-like prose.

## Durable correction

Apply the same explicit contract to every prompt branch that can produce a visible reply:

- visible output defaults to 1–2 short sentences;
- French, tutoiement, natural/direct/relaxed tone;
- simple words, no ceremonial opening;
- no repetition of the user turn or full brief;
- expand only on an explicit request for details, a list, or a recap;
- contextual `<telegram_choices>` remains machine-only and outside the sentence budget.

For Scena Cloudflare, the two relevant surfaces were:

- `workers/api/src/agent.ts`: global Telegram/system prompt;
- `workers/api/src/index.ts`: guided-intake continuation envelope.

Fixing only one leaves inconsistent behavior depending on routing.

## Regression shape

Assert against the actual model request payload, not the source file text:

- regular agent/planner payload contains `1 à 2 phrases courtes`;
- regular payload contains `ton naturel, direct et détendu`;
- guided-intake payload contains both markers;
- existing state, approval, multimodal, and contextual-button behavior remains green.

Focused Scena verification bundle:

```bash
node --experimental-strip-types --test \
  tests/agent-communication.test.mjs \
  tests/telegram-ui.test.mjs \
  tests/openrouter-agent-llm.test.mjs
```

After Worker deployment, verify `/health` on both the custom domain and workers.dev endpoint. Health proves deployment/routing, while behavioral correctness remains covered by payload-level tests; do not inject a synthetic message into a real tenant chat merely for a smoke test.
