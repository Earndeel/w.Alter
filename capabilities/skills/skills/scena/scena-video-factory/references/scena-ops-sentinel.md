# Scena Ops / Scena Sentinel Pattern

Session-derived architecture pattern for Scena operational autonomy.

## Trigger
Use when Lucas asks for Scena to have its own operational brain/agent, daily integrity checks, automatic repair, system coordination, or generative-AI technology watch.

## Core decision
Keep Scena runtime data and ops/autonomy data separate:

```txt
scena-db      = runtime product data
               clients, jobs, credits, Scena Chat, Scena Connect

scena-ops-db  = operational intelligence
               health checks, incidents, repair actions, metrics, AI watch, recommendations
```

This prevents maintenance/research logs from polluting or risking the product runtime DB.

## Naming
- **Scena Engine**: shared creative/generation engine.
- **Scena Chat**: current Telegram multi-tenant experience.
- **Scena Connect**: SaaS API/connector layer.
- **Scena Ops**: internal operations/control layer.
- **Scena Sentinel**: daily autonomous operational agent.
- **Scena Ops DB**: dedicated D1 DB for Sentinel state and audit.

## Recommended D1 tables
Create a separate D1 database, usually `scena-ops-db`, with tables like:

```txt
ops_systems              registry of systems to monitor
ops_runs                 daily/manual Sentinel executions
ops_checks               check results per run/system
ops_incidents            open/resolved incidents
ops_repair_actions       safe/guarded/manual repair audit
ops_metric_snapshots     time-series-ish metrics snapshots
ops_research_sources     AI-watch sources
ops_research_items       captured model/provider/news items
ops_recommendations      actionable product/tech recommendations
ops_agent_notes          runbooks, lessons, policies
ops_audit_log            append-only audit trail
```

## Sentinel daily flow

```txt
1. collect
2. diagnose
3. safe_autofix
4. verify
5. research_watch
6. recommend
7. report
```

## Integrity checks
Cover at least:
- Worker health: `/health`, `/ping`, admin critical routes.
- D1 runtime schema: clients, image/video jobs, credits, agent logs, SaaS tables.
- D1 Ops schema.
- Pages: admin + portal.
- Secrets presence: Kie, OpenRouter, Stripe, Telegram, etc.
- Stripe webhook enabled.
- Telegram routing and delivery markers.
- Scena Connect endpoints and webhook signing.
- Jobs stuck in `processing`/`submitted` and completed-but-undelivered jobs.
- Provider route config and payload contracts.
- Recent recurring errors in `agent_log`.

## Repair policy

### Safe autofix allowed
Only non-destructive, low-risk actions:
- repoll stuck provider jobs
- retry Telegram delivery for completed-but-undelivered jobs
- seed missing built-in presets/config rows
- close duplicate/resolved incidents after verification
- refresh provider catalog cache
- record diagnostics/recommendations/reports

### Guarded only / needs approval
Never auto-apply without explicit approval:
- D1 migrations
- production provider route changes
- pricing/credit changes
- auth/secrets changes
- deploy/rollback Worker or Pages
- bulk client-data mutations

### Never automatic
- permanent deletion of client data
- secret rotation without validation
- active Stripe billing mutation
- major runtime architecture changes

## Generative AI watch
Initial sources worth seeding:
- Artificial Analysis
- Kie.ai Market/docs
- Fal.ai models/docs
- OpenRouter rankings
- Replicate blog/models
- Hugging Face Papers

Classify findings by modality (`video`, `image`, `audio`, `llm`, `agent`, `infra`), score relevance/cost/quality/novelty, and create recommendations. Do **not** automatically change production routes from research findings; open recommendations or guarded repairs instead.

## Worker integration sketch
Add an `OPS_DB` binding:

```toml
[[d1_databases]]
binding = "OPS_DB"
database_name = "scena-ops-db"
database_id = "..."
```

Suggested modules:

```txt
workers/api/src/ops_db.ts
workers/api/src/ops_checks.ts
workers/api/src/ops_repairs.ts
workers/api/src/ops_research.ts
workers/api/src/ops_agent.ts
workers/api/src/ops_admin.ts
```

Suggested admin routes:

```txt
GET  /api/admin/ops/runs
GET  /api/admin/ops/runs/:id
GET  /api/admin/ops/incidents
GET  /api/admin/ops/recommendations
POST /api/admin/ops/run
POST /api/admin/ops/repair/:id/approve
POST /api/admin/ops/recommendations/:id/decision
```

## Reporting format
Daily report should be concise and operator-oriented:

```txt
Scena Sentinel — Daily Report
Status global: OK / WARN / FAIL

Checks:
- API Worker: OK
- D1 runtime: OK
- Jobs bloqués: 2 réparés
- Telegram delivery: 1 retry OK
- Kie provider: WARN crédits bas
- Scena Connect: OK

Auto-fixes:
- Re-polled 2 jobs
- Delivered 1 completed video

Incidents:
- Kie credits low — monitoring

Veille IA:
- Nouveau modèle X intéressant pour image-to-video

Recommandations:
1. Tester modèle Y pour UGC 9:16
2. Ajouter fallback provider Z pour images produit
```

## Session artifacts from May 2026
In `/root/projects/scena-cloudflare/` a first draft was created:
- `d1/scena-ops-db.sql`
- `docs/scena-ops-agent.md`
- `docs/plans/2026-05-08-scena-ops-sentinel.md`
