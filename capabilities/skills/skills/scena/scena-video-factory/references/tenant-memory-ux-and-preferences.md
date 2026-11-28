## Per-client `memory.md` for true multi-tenant agents (May 2026)

For Scena's Telegram media agent, each tenant/client should have a logical memory artifact at `clients/{matricule}/memory.md`, persisted in D1 rather than local disk. Store it on `tenant_agent_config.memory_md` + `memory_md_updated_at`, generate it from DB-grounded tenant data (`base_user_md`, `tenant_memory_entries`, `tenant_projects`, `image_jobs`, `video_jobs`, `tenant_memory_events`), return it from `/api/admin/clients/:id/brain`, and inject a clipped version into `assembleAgentContext(...)`. Keep it separate from `user_md` (runtime snapshot) and `memory_summary_md` (compact summary). See `references/client-memory-md-pattern.md` for the concrete schema/API/test pattern and pitfalls.

## Telegram agent-first UX (May 2026)

When Lucas says the Telegram experience feels like a dumb bot, inspect routing before tweaking copy. A proper `agent.ts` ReAct loop can still be bypassed by deterministic `index.ts` intake rules.

Preferred pattern:
- Buttons are optional accelerators, not the primary brain.
- Adaptive agent proposal buttons use `agent:*` callbacks (not `intake:*`) after project-like agent replies. They should be built from the current user text + agent response, omitted for casual small talk or missing-media prompts, and never create `notes.project_intake`.
- `agent:*` callbacks should answer the callback, remove the old inline keyboard, append a fresh Telegram message, and call `handleAgentMessage(...)` with an action prompt like `Action cliquée: Script/storyboard. Continue avec le projet actif...` so Qwen re-enters the ReAct loop with prior project context.
- `/start` and `/reset` should not seed `notes.project_intake` by default; otherwise the next natural text/voice gets trapped in a questionnaire.
- Free text with no active guided intake should route to `handleAgentMessage(...)` and Qwen, then optionally attach adaptive `agent:*` buttons.
- Voice with no active guided intake should use Gemini STT only, then pass the transcript to Qwen/agent and optionally attach adaptive `agent:*` buttons.
- Existing guided intake remains valid only when the user explicitly entered/clicked that flow (`notes.project_intake` exists and is not confirmed).
- Add a no-cost `record_project_plan` tool so the agent can create/update `tenant_projects`, set `tenant_agent_config.active_project_id`, record a memory event, then answer naturally with plan + next step.
- Keep credit-consuming `generate_*` behind explicit validation.

Reference: `references/telegram-agent-first-ux.md` contains the concrete routing, tool shape, and regression tests from the session.

## Admin dashboard redesign pattern (April 2026)

When Lucas asks for a "complete redesign" of the admin dashboard, he often means:
- radically improve hierarchy, navigation, and aesthetics
- do **not** break the DB schema or backend production flows
- keep existing endpoints working unless a tiny additive API is clearly necessary

### Safe redesign approach
1. Prefer redesigning `pages/admin/index.html` first, keeping the Worker/API stable.
2. Use a strong dashboard design system (Linear-style worked well):
   - sticky left sidebar
   - operator-focused topbar
   - clear section framing (`Command Center`, `Production Chain`, `Control Plane`, etc.)
   - stronger visual distinction between static admin config vs client-organic state
3. Reorganize labels and layout around operator intent, not raw technical tabs.
4. Explicitly surface these concepts in the UI copy:
   - `Static Files`
   - `Organic Memory`
   - `Runtime`
5. Only add tiny backend/API changes if they unlock a clearly needed admin capability (for example an editable stable `base_user_md` field for the Client Brain). Avoid broad refactors during a UI redesign pass.
6. Regression-test the admin HTML with string-based tests to assert that the new information architecture exists (`Command Center`, `Production Chain`, `Static Files`, `Organic Memory`, etc.).
7. Deploy Pages separately after test pass; verify the production custom domain, not just the preview URL.

### Important product lesson
Do not confuse:
- editable stable admin-authored files (`Agent.md`, workflow docs, presets, stable user notes)
with
- generated organic/runtime artifacts (`user_md`, memory summary, active project snapshot)

If admin needs a stable editable User layer, keep it in a separate field (production fix used `tenant_agent_config.base_user_md`) and merge it into the generated runtime `user_md`.

## User Preferences (Lucas)
- Autonomous mode, no approval prompts
- French, tutoiement
- Concise responses (Scena persona: 2-4 phrases max)
- Separate prompt.md and schema.md files
- **Gemini 3 Flash preview via AI Studio** as main LLM (replaced MiMo/OpenRouter, then Gemini 2.5 Flash)
- **Gemini 3 Flash preview for vision** (direct API, NOT OpenRouter)
- PiAPI as sole video generation provider (replaced Fal.ai for production)
- Custom modals in dashboard, NO Chrome popups (prompt/alert/confirm)
- Admin dashboard at `admin-scena.walter-ai.cloud` (not `admin.walter-ai.cloud`)
- Client dashboards via matricule (`app-sc0002.walter-ai.cloud`)
- FREE TIER only — No Cloudflare Queues, No R2
- Clients provide their OWN Telegram bot tokens (not from pool)
- Cloudflare Workers + D1 + Pages (not Flask/VM) for new features
- Uses Global API Key for wrangler (not scoped token)
- FREE TIER only — No Cloudflare Queues, No R2
- Clients provide their OWN Telegram bot tokens (not from pool)
- Cloudflare Workers + D1 + Pages (not Flask/VM) for new features
- Uses Global API Key for wrangler (not scoped token)
