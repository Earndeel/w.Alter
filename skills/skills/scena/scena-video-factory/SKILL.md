---
name: scena-video-factory
description: Multi-tenant AI video agent factory V3 — Scena. Cloudflare Workers + D1, PiAPI webhook flow, multi-tenant Telegram routing, Better Auth, Stripe billing. Kimi 2.6 orchestrator via OpenRouter. FREE TIER architecture.
category: devops
---

# Scena Video Agent Factory V2

**Reference files:** `references/gemini-veo-integration.md` — Veo 3.1 Lite via Gemini API (SDK, polling, pricing, Scena integration plan)
`references/pipeline-api-contracts.md` — Full API contracts for POST /api/saas/pipeline, status polling, webhook events, step definitions, BYOK.
`references/workflow-lab-client-demo-may-2026.md` — Client demo + Workflow Lab pattern: demo page, per-step admin controls, Seedance payload preview endpoint, tests, HTML-writing verification.

## Always-on rules

- Scena is a PROPER agent — the LLM decides which tools to call, not hardcoded logic.
- Scena Chat (Telegram multi-tenant flow) must stay intact. Scena for SaaS is an additive API/connector layer into the same Scena Engine, not a replacement product.
- Use model/provider config, don't hardcode.
- NEVER expose Telegram URLs (contain bot_token) to PiAPI.
- NO secrets in HTML.
- Live D1 can drift from local schema: before migrations, inspect prod with `PRAGMA table_info(...)` and `PRAGMA index_list(...)`.
- Always check with `wrangler pages project list` before deploying.
- Always investigate with `agent_log` D1 table before assuming the root cause.
- Always run the FULL test suite after any changes to the ReAct loop or webhook handler.
- Deploy after code changes (wrangler deploy + pages deploy).
- Do not remove Kie blindly. Keep the provider adapters explicit and route by connection/workflow.

## References (read with skill_read(name, file_path=...))

- `references/client-memory-md-pattern.md` — Read when implementing or editing per-client memory.md and its persistence.
- `references/cloudflare-architecture-and-agent.md` — Read when working on Worker architecture, tenant routing, agent orchestration, authentication, or migration history.
- `references/fal-generation-and-tool-chaining.md` — Read when changing Fal model selection, image-to-video chaining, ReAct async boundaries, or background polling.
- `references/fal-kie-pipeline-repair.md` — Read when repairing dual-provider Fal/Kie routing, adapters, callbacks, or BYOK contracts.
- `references/fal-only-pipeline-audit.md` — Read when auditing a Fal-only pipeline configuration.
- `references/fal-pipeline-patterns.md` — Read when implementing Fal pipeline integration patterns.
- `references/gemini-veo-integration.md` — Read when integrating Veo 3.1 Lite through the Gemini API, including SDK calls, polling, and pricing.
- `references/legacy-factory-and-infrastructure.md` — Read for the historical VM factory, CLI, tunnels, authentication, URLs, and environment configuration.
- `references/ops-sentinel-overview.md` — Read when planning Scena operational monitoring, integrity checks, safe repair, or provider watch.
- `references/original-comfyui-scena-bridge-may-2026.md` — Read when investigating the original ComfyUI-to-Scena bridge.
- `references/pipeline-and-workflow-runners.md` — Read when implementing or debugging pipeline execution, workflow persistence, async callbacks, or source-video regeneration.
- `references/pipeline-api-contracts.md` — Read when implementing pipeline requests, status polling, webhook events, step definitions, or BYOK API contracts.
- `references/pitfalls-april-17.md` — Read when investigating failures covered by the April 17 troubleshooting notes.
- `references/saas-connect-and-portal.md` — Read when changing SaaS connections, BYOK, the self-service portal, or admin connection controls.
- `references/scena-ops-sentinel.md` — Read when implementing the detailed Scena Ops or Sentinel workflow.
- `references/scena-p0-hardening-may-2026.md` — Read when working on Scena production hardening and P0 fixes.
- `references/scena-production-readiness.md` — Read when assessing Scena production readiness.
- `references/scena-vitrine-redesign-may-2026.md` — Read when redesigning the public Scena showcase.
- `references/source-video-workflow-runtime-may-2026.md` — Read when implementing the runtime for source-video-to-target regeneration.
- `references/telegram-agent-first-ux.md` — Read when fixing Telegram routing that bypasses the agent or changing agent-first conversation behavior.
- `references/tenant-memory-ux-and-preferences.md` — Read when changing tenant memory, Telegram conversation routing, dashboard design, or Scena-specific user preferences.
- `references/troubleshooting-and-lessons.md` — Read before diagnosing production failures or changing schemas, provider payloads, Telegram delivery, or retry handling.
- `references/workflow-control-center-may-2026.md` — Read when changing workflow administration and control-center behavior.
- `references/workflow-lab-client-demo-may-2026.md` — Read when building client demos, Workflow Lab controls, Seedance payload previews, or verifying generated HTML.
