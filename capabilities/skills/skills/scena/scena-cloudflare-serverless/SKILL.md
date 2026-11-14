---
name: scena-cloudflare-serverless
description: Scena V2 — Cloudflare serverless architecture (Workers + D1 + Pages) replacing Flask/VM. Multi-tenant Telegram bot routing, zero-storage media proxy, PiAPI webhook async flow, agent brain with Mimo v2 Pro.
category: devops
---

# Scena Cloudflare Serverless V2

## Always-on rules

- "Bot token never leaves D1."
- "For Scena's Telegram UX, don't let the agent jump straight to generation on every clear request."
- "Use a guided intake layer before the free-form agent when the user starts a project."
- "Use a 4-stage generation approval policy with **two distinct durable transitions**:"
  - "vague brief": "no production tool call"
  - "clear brief, not yet recorded": "call `record_project_plan` (control-plane tool, always allowed even if a workflow run exists)"
  - "brief approval": "create the D1 `workflow_run`, then confirm `Brief validé et enregistré`; never claim this before the D1 write succeeds"
  - "show the credit estimate and ask for a separate production launch"
  - "production approval": "reject planning/cadrage/brief language as production approval"; "only then allow `generate_*`"
- "OpenRouter primary LLM for Scena agent/intake should be `qwen/qwen3.6-plus` unless Lucas explicitly changes routing."
- "When a Cloudflare Pages frontend calls a Worker API, CORS headers must be manually added to EVERY response."
- "Wrangler vars in wrangler.toml conflict with secrets of same name — use secrets only"
- "Use global key for D1 migrations:"
- "Always check `wrangler pages project list` before deploying — project name != domain name."
- "Never do sync polling for video generation — always submit and wait for webhook"
- "The `saas_pipeline_runs` table is separate from `workflow_runs` (which is for the chat-agent flow). Don't mix them."
- "Scena uses the Oracle VM only for deterministic zero-credit post-production after provider-generated clips."

## Architecture

```
api.walter-ai.cloud → Cloudflare Worker (scena-api)
                        ├── /webhook/telegram/{matricule}  ← Multi-tenant Telegram
                        ├── /webhook/piapi                 ← Video callback
                        ├── /webhook/piapi-image           ← Image callback
                        ├── /webhook/fal-image             ← Fal.ai fallback
                        ├── /proxy/media/{file_id}?client= ← Zero-storage proxy
                        ├── /api/register                  ← Client signup
                        ├── /api/bot/validate              ← Bot token → webhook
                        └── /api/admin/*                   ← Admin API
```

## References (read with skill_read(name, file_path=...))

- `references/deployment-and-d1.md` — Read before Worker deployment, Cloudflare authentication or secret changes, D1 migrations or queries, DNS changes, or debugging D1 access.
- `references/media-worker.md` — Read when changing or deploying the Oracle FFmpeg sidecar, signed jobs and callbacks, or verifying video composition end to end.
- `references/pages-telegram-and-admin.md` — Read before Pages deployment or changes to Telegram intake, voice handling, brief and production approvals, workflow gating, admin UI, or CORS; also covers video URL validation and subrequest mitigation.
- `references/runtime-patterns.md` — Read when changing multi-tenant routing, media proxying, PiAPI callbacks, agent state, model routing, style presets, or prompt injection.
- `references/saas-pipeline.md` — Read when implementing or debugging SaaS pipeline steps, BYOK, polling limits, async resume, analysis, or progression webhooks.
- `references/troubleshooting.md` — Read when diagnosing Worker runtime failures, provider failures, admin sessions, D1 anomalies, Stripe secrets, or Worker test and OpenRouter migration failures.
- `references/video-providers.md` — Read when adding or changing a video provider, its model catalog, credentials, payloads, job tracking, routing, or webhook handler.
