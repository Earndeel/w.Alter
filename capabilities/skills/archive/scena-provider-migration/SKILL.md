---
name: scena-provider-migration
description: Audit and execute provider migrations in Scena Cloudflare Workers — Fal.ai ↔ Kie.ai ↔ PiAPI. Maps all active generation routes, defaults, callbacks, recovery jobs, and tests to exact file:line references, then produces minimal coherent migration plans.
category: devops
---

# Scena Provider Migration

When migrating Scena's primary generation provider (e.g. Fal → Kie or Kie → Fal), do a read-only audit first. Never delete the old provider — keep it as fallback/legacy. Only change **defaults**, not the fallback branches.

## Trigger

- User asks to audit or migrate Scena's generation provider (Fal.ai, Kie.ai, PiAPI)
- User asks "where does Scena use Fal" / "what routes go through Kie"
- Preparing a dual-provider mode switch

## Audit Checklist (read-only)

Run this before any edits:

1. **Runtime defaults** — search for `|| 'fal'`, `|| 'kie'`, `=== 'fal' ?`, `=== 'kie' ?` in:
   - `workers/api/src/agent.ts` (chat agent submit functions)
   - `workers/api/src/saas_connect.ts` (SaaS submit + presets + createConnection)
   - `workers/api/src/pipeline_runner.ts` (autonomous pipeline submit + fallback)
   - `workers/api/src/orchestration_config.ts` (BUILTIN_MODEL_CATALOG entries)
   - `workers/api/src/provider_payloads.ts` (contracts, sanitizers, builders)

2. **Webhook routes** — grep `index.ts` for `/webhook/` paths, map each to its handler

3. **Cron recovery** — check `scheduled()` in `index.ts` for recovery sweeps

4. **Polling functions** — find `poll*Result` functions in `agent.ts`

5. **D1 schema** — check `fal_endpoint` column, `***` column, indexes on provider columns, seed data for `provider_hint` / `default_provider`

6. **Ops/sentinel** — `ops_checks.ts` for provider binding checks, `ops_research.ts` for provider monitoring sources

7. **Tests** — search test files for mocked provider URLs (`fal.run`, `queue.fal.run`, `api.kie.ai`) and `default_provider` / `provider_hint` assertions

8. **D1↔TypeScript discrepancy** — compare D1 seed SQL (`saas-connect.sql`, `scena-saas-db.sql`) against the in-memory presets in `saas_connect.ts`

9. **Callback and credit hardening gate** — for every new-provider callback and poller, prove exact task-ID correlation, provider-authenticated status/output verification, idempotent terminal transitions, and side effects only after a winning transition. Use the `scena-security` reference `references/provider-webhook-hardening.md`.

10. **Verification tiers** — run provider payload/routing tests first, then every migration-touched behavioral test, then Worker dry-run/build, then the global suite. Report migration-green tests separately from unrelated pre-existing UI drift; never call the global suite green when it is not.

## Migration Plan Shape

After audit, produce a plan with these sections in order:

1. **Défauts runtime à changer** (exact file:line:old:new table)
2. **Pipeline runner fallbacks**
3. **Cron recovery à ajouter** (never remove old recovery, add new in parallel)
4. **Tests à mettre à jour** (non-blocking, list files + lines)
5. **D1 seed alignment** (if TS and D1 disagree)
6. **Pièges** (columns with legacy names, polling functions to clone)

## Pitfalls

- **Colonne `image_jobs.fal_endpoint`** est utilisée même pour les tâches Kie. Ne pas renommer.
- **Colonne `image_jobs."***"`** est un nom legacy. La normaliser dans l'API admin, pas dans le schéma.
- **Tool redaction is not source text.** Provider-prefixed identifiers and columns can be masked in snapshots or diffs. Never paste a redacted token into a patch or migration; re-read the exact file or verify the identifier from executable schema metadata first.
- **Les fonctions `pollFal*`** sont les fonctions de polling primaires. Créer des équivalents `pollKie*` plutôt que renommer.
- **D1 seed `ON CONFLICT DO UPDATE`** peut écraser les changements TS si les deux ne sont pas alignés.
- **`saas_connect.ts` presets in-memory** peuvent diverger des seeds D1 — comparer systématiquement.
- **Skill `scena-cloudflare-serverless` a une instruction périmée** : le pitfall "Adding a New Video Provider" dit encore `requestedProvider || 'fal'`. Le défaut correct est `requestedProvider || 'kie'` (le skill est manually-authored donc non modifiable ici).

## Reference

`references/fal-to-kie-migration-audit-2026-07.md` — Complete audit of every active Fal.ai route in Scena as of 2026-07-22, with exact file:line references and migration plan.
