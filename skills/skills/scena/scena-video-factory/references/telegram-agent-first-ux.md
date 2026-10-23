# Telegram agent-first UX for Scena

Session lesson: if Lucas says Scena feels like a dumb bot, inspect whether Telegram is bypassing the real ReAct agent with a deterministic intake/state machine.

## Root cause pattern

The Worker can contain a proper `agent.ts` ReAct loop, but Telegram can still feel bot-like if `index.ts` routes too many messages into hardcoded flows:

- `/start` or `/reset` creates `notes.project_intake`, so the next natural text/voice message is trapped into guided buttons.
- Voice messages are transcribed, then routed into intake synthesis instead of the natural agent.
- Phrases like `je veux une vidéo...` trigger `shouldStartProjectIntake(...)` and bypass Qwen chat/tool-calling.
- Summary-stage intake repeats recap/parameters instead of acknowledging the user's new intent.

## Desired routing

Keep buttons as optional accelerators, not the primary brain.

- `/start`: introduce Scena + optional entry buttons, but do not create `project_intake` by default.
- `/reset`: clear notes/context/memory and restart the visible start flow; do not lock the next message into intake.
- Free text with no active guided intake: route to `handleAgentMessage(...)`.
- Voice with no active guided intake: Gemini STT only, then route transcript to `handleAgentMessage(...)` with Qwen.
- Existing guided intake remains valid only when `notes.project_intake` already exists and `stage !== 'confirmed'`.
- Image + explicit video cue can still open the deterministic video picker for parameter confirmation.

## Agent project-plan tool

Add a no-cost tool like `record_project_plan` so Qwen can persist understanding before execution:

- Creates/updates `tenant_projects`.
- Updates `tenant_agent_config.active_project_id`.
- Records a `tenant_memory_events` event such as `project_plan_recorded`.
- Stores: `project_name`, `brief_md`, `plan_md`, `constraints_md`, `next_step`, `status`.

System prompt rule:

- When the client describes a project/intention/constraint/preference, call `record_project_plan` before responding.
- After the tool result, answer naturally: what was understood, proposed plan, missing info, next step.
- Never call credit-consuming `generate_*` without explicit validation.

## Regression tests to add

- Free-text project brief with no active intake goes to Qwen agent, not `project_intake`.
- Voice message uses `gemini-3.1-flash-lite-preview` only for STT, then Qwen receives the transcript.
- `/reset` clears guided intake instead of seeding `project_intake.stage='entry'`.
- Agent can call `record_project_plan`, persist a tenant project, then synthesize a natural response.
- Existing button-driven intake still works when the client explicitly clicks intake callbacks.

## Deployment discipline

Because this is a product/UX architecture change, commit locally and run full tests, but do not deploy/push without Lucas review.