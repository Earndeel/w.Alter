# Scena Luna/Sol multimodal intake — July 2026

## Scope

Concrete migration in `/root/projects/scena-cloudflare` for a multi-tenant Telegram agent on Cloudflare Workers + D1.

## Final routing

| Stage | Runtime |
|---|---|
| Natural conversation | OpenRouter `openai/gpt-5.6-luna`, `reasoning.effort=high` |
| Guided structured intake | Same Luna high route |
| Image understanding | Image proxy URL sent directly to Luna as `image_url` content |
| Voice understanding | Gemini deterministic STT, then transcript marked `TRANSCRIPTION_AUDIO_CLIENT` and analyzed by Luna high |
| Planning | OpenRouter `openai/gpt-5.6-sol`, `reasoning.effort=xhigh`, invoked only after Luna emits an awaiting-validation project plan |
| Execution | Existing deterministic workflow runner, still gated by explicit approval |

OpenRouter metadata at the time advertised Luna inputs as text/image/file, not audio. Therefore Gemini remained only the faithful transcription adapter; Luna remained the semantic intake brain.

## Key code changes

### Conversation loop

The old flow called Sol before every Luna turn. The repaired flow starts with Luna and keeps `plannerPlan` empty. When Luna calls `record_project_plan` with `status="awaiting_validation"`:

1. serialize Luna's grounded tool arguments into a `LUNA_COLLECTED_BRIEF` handoff;
2. call Sol once;
3. replace `toolArgs.plan_md` with Sol's plan;
4. persist through the existing tool;
5. expose the planner plan to Luna on the next iteration if another turn is needed.

A planning failure must not erase Luna's collected brief.

### Image turns

The canonical message builder emits:

```json
[
  {"type":"text","text":"<client turn + intake instructions>"},
  {"type":"image_url","image_url":{"url":"<fresh proxy URL>"}}
]
```

The separate Gemini vision-summary call was removed from the conversation path. Luna now receives visual evidence directly.

### Guided-intake bypass

`index.ts` had a deterministic `project_intake` branch that could bypass the natural agent. It was updated so:

- structured extraction calls Luna high;
- conversational objections inside guided intake call the same Luna agent;
- fresh `pending_proxy_url` is threaded into both branches;
- a photo sent earlier is not dropped on the next guided text turn.

### Voice turns

Telegram audio still follows:

1. fetch Telegram file;
2. Gemini STT with a prompt requiring faithful transcription only;
3. route transcript to Luna with internal audio-source metadata;
4. Luna extracts planning data and asks for missing fields.

Do not tell users that Luna consumed raw audio on this route.

## Regression changes

Targeted behavioral suite:

```bash
node --experimental-strip-types --test \
  tests/openrouter-agent-llm.test.mjs \
  tests/agent-communication.test.mjs \
  tests/telegram-ui.test.mjs \
  tests/workflow-runner.test.mjs
```

Validated invariants:

- Luna model ID + high reasoning;
- Sol model ID + xhigh reasoning;
- image proxy in a real `image_url` content part;
- voice STT precedes Luna and includes the audio marker;
- guided intake retains fresh images;
- first incomplete turn has no `SCENA_PLANNER_PLAN`;
- Sol runs only after Luna marks the brief awaiting validation;
- Sol output is persisted;
- execution approval remains mandatory.

Removing eager Sol planning reduced model call counts. One workflow test previously mocked `planner → tool call → final response`; after the change, an async generation tool could return its final Telegram text from the first Luna call, so the correct expected count became one. Fix the mock sequence—do not reintroduce an unnecessary planner/model call merely to satisfy an old fixture.

## Verification result

- Targeted tests: 39/39 passed.
- Wrangler dry-run: successful.
- Worker deployed as version `28916fa0-6d82-48ab-9a88-4bad388acbcd`.
- Live Worker `/health`: HTTP 200 after deploy.

The broad repository suite also contained unrelated dirty-worktree admin/UI failures. Keep those separate unless the routing change reproduces them directly.