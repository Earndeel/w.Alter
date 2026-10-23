# Scena per-client `memory.md` pattern

Use this when evolving Scena into a real multi-tenant media agent where each Telegram client has durable memory.

## Goal

Each client must have an isolated memory artifact equivalent to:

`clients/{matricule}/memory.md`

In Cloudflare Workers/D1, this should usually be a logical path + D1-persisted content, not a filesystem write. Workers have no durable local disk, and D1 keeps tenant isolation explicit.

## Recommended D1 fields

Extend `tenant_agent_config` with:

```sql
ALTER TABLE tenant_agent_config ADD COLUMN memory_md TEXT DEFAULT '';
ALTER TABLE tenant_agent_config ADD COLUMN memory_md_updated_at TEXT DEFAULT '';
```

Also update canonical schema files, not only migrations:

- `d1/schema.sql`
- `d1/schema-v2.sql`
- migration e.g. `d1/migrations/003_client_memory_md.sql`

## Memory file contents

Generate `memory.md` from DB-grounded tenant data only. Good sections:

- `# memory.md — {matricule}`
- generated timestamp and client id
- client profile: name, email, matricule, Telegram bot username, status
- stable admin/user notes from `tenant_agent_config.base_user_md`
- durable preferences/facts from `tenant_memory_entries`
- organic summary from `memory_summary_md` / client summary
- recent projects from `tenant_projects`
- recent image jobs from `image_jobs`
- recent video jobs from `video_jobs`
- agent timeline from `tenant_memory_events`

Never include bot tokens, API keys, Stripe secrets, provider keys, or raw credentials.

## Runtime integration

In `assembleAgentContext(...)`:

1. Load/create `tenant_agent_config` via `ensureTenantAgentConfig`.
2. Build `user.md` and `memory_summary_md` as before.
3. Build `memory.md` from D1 rows.
4. Persist `memory_md` + timestamp to `tenant_agent_config`.
5. Inject a clipped memory-file section into `compiledContextMd`.

Keep context bounded (e.g. full D1 field clipped around 20k chars, prompt injection around 5k chars). Preserve the separate roles:

- `base_user_md`: stable admin-authored notes.
- `user_md`: generated runtime snapshot.
- `memory_summary_md`: compact organic summary.
- `memory_md`: readable per-client long-form memory artifact.

## Admin API pattern

Add/keep:

- `GET /api/admin/clients/:id/brain`
- `PUT /api/admin/clients/:id/brain`

GET should return:

```json
{
  "client": { "...": "safe client fields only", "telegram_bot_configured": true },
  "config": { "...": "tenant_agent_config", "memory_md": "..." },
  "memory_file": {
    "path": "clients/sc0003/memory.md",
    "content": "# memory.md — sc0003\n...",
    "updated_at": "..."
  },
  "workflow_assignments": [],
  "metrics": {
    "video_jobs": 0,
    "image_jobs": 0,
    "projects": 0,
    "workflow_runs": 0
  }
}
```

PUT should update stable editable config (`agent_version`, `persona_md`, `system_overrides_md`, `base_user_md`, max limits), then regenerate `memory.md`.

## Testing pattern

Use existing Worker regression harness:

```bash
node --experimental-strip-types --test tests/worker-regressions.test.mjs
node --experimental-strip-types --test tests/workflow-library.test.mjs
npm test
```

Add assertions that:

- `memory_file.path` is `clients/{matricule}/memory.md`.
- content starts with `# memory.md — {matricule}`.
- content includes base user notes, durable memory entries, projects, image/video jobs, and memory events.
- `assembleAgentContext` returns `memoryFile` and includes a clipped `Client memory file` section in `compiledContextMd`.
- response never exposes `telegram_bot_token`.

## Pitfalls

- Do not implement per-client memory as local filesystem files in Cloudflare Workers.
- Do not overwrite `base_user_md` with runtime-generated `user_md`.
- Do not use previous `memory_summary_md` as input to generate a new summary recursively; regenerate from stable facts + client summary.
- In tests, mock SQL matching can be brittle if multiline SQL strings do not include the expected contiguous substring; keep key clauses on one line when tests match via `sql.includes(...)`.
- Always run full `npm test` after changing webhook, ReAct, scheduled, or agent-context logic; targeted tests can pass while Telegram/cron regressions remain.
