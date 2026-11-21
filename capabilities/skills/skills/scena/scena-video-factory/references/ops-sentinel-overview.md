## Scena Ops / Scena Sentinel (May 2026)

When Lucas asks for a dedicated Scena operational brain, daily integrity checks, safe auto-repair, or AI-model/provider watch, use the **Scena Ops / Scena Sentinel** pattern. Keep runtime product data in `scena-db` and create a separate `scena-ops-db` for operational checks, incidents, repair actions, metrics, research items, and recommendations.

Core rule: Sentinel may auto-apply only safe, non-destructive repairs (repoll stuck jobs, retry completed-but-undelivered Telegram delivery, reseed built-ins, close verified duplicate incidents, write reports/recommendations). D1 migrations, provider-route changes, pricing/credits, auth/secrets, deploy/rollback, and bulk data mutations are guarded repairs requiring explicit approval.

Reference: `references/scena-ops-sentinel.md` contains the schema shape, daily flow, checks, repair policy, research-watch sources, admin routes, and report format. Production is installed with D1 `scena-ops-db` bound as `OPS_DB` (`database_id=cfedbcb0-6788-400b-a577-6369dda355df`). Session artifacts in `/root/projects/scena-cloudflare/`: `d1/scena-ops-db.sql`, `docs/scena-ops-agent.md`, `workers/api/src/ops_*.ts`, and `tests/ops-sentinel.test.mjs`.

Reference: `references/scena-production-readiness.md` captures the production-readiness audit pattern, P0 blockers, audit commands, and partner-ready Scena Connect criteria. Use it when Lucas asks what is missing before launch or before onboarding SaaS partners.

Reference: `references/scena-p0-hardening-may-2026.md` captures the concrete P0 hardening run: Scena Connect key rotation/revoke, quotas, rate limit, usage ledger, webhook delivery audit/retry/idempotency, Sentinel Telegram notifications, historical job cleanup, D1 `updated_at` drift pitfall, test/deploy sequence, and final prod verification.

Reference: `references/scena-vitrine-redesign-may-2026.md` captures the public-site redesign pattern: multi-page `pages/portal` structure, preserving the authenticated client dashboard/checkout contract inside `index.html`, Scena Connect developer copy requirements, TDD checks, local preview/screenshot workflow, secondary-page `window.showSignIn` pitfall, and Lucas's no-production-Pages-deploy-before-visual-review rule.

Reference: `references/source-video-workflow-runtime-may-2026.md` captures the runtime pattern for Scena source-video → target-video regeneration: `workflow_artifacts` metadata table, `recordWorkflowArtifact` / `listWorkflowArtifacts`, source-video Telegram intake (`message.video` and video documents), `[SOURCE_VIDEO_PROXY_URL]` injection, fresh follow-up reuse for `vas y`, and tests for `prepare_video_artifacts`, `analyze_video_source`, and `build_modification_plan`.

Reference: `references/workflow-control-center-may-2026.md` captures the Workflow Control Center pattern: admin endpoints for `workflow_runs` live summaries/details, per-run `workflow_step_runs.input_json.admin_control` prompt/input overrides, admin UI live timeline/trace/artifacts/media jobs, tests, deployment verification, and prod D1 schema drift pitfall (`image_jobs.input_prompt`, not `prompt`).

Reference: `references/workflow-lab-client-demo-may-2026.md` captures the Scena demo + Workflow Lab pattern: a prospect-facing `pages/portal/demo.html`, a deeper operator `pages/admin/operator.html`, `/api/admin/workflow-lab/config`, `/payload-preview` for sanitized Kie Seedance payloads, required regression tests, and the large-HTML/script-parse verification pattern.
