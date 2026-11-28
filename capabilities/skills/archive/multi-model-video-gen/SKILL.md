---
name: multi-model-video-gen
category: ad-pipeline
description: Multi-model video generation system — parameterized pipeline supporting multiple AI video models via Fal.ai, with Higgsfield MCP as primary and FAL direct API as fallback
created: 2026-04-08
---

# Multi-Model Video Generation

Add support for multiple video generation models (Kling, Runway, Veo, etc.) to a pipeline that was originally hardcoded to one model.

## Key Insight

The LLM generates a JSON payload to send to Fal.ai. Each model is 3 files:
- **config.json** — `{\"name\": \"...\", \"endpoint\": \"fal-ai/...\"}` (used by code)
- **prompt.md** — system prompt for the LLM (instructions + rules + output format)
- **schema.md** — API reference text (params, types, constraints, examples)

The LLM receives 4 things: `prompt.md` (system), `schema` (user section), `analysis` (from DB), `comments` (from DB). It outputs JSON.

**Keep config.json minimal** — just `name` + `endpoint`. No `modes`, `provider`, `supports_*` flags. The prompt.md and schema.md are plain text, not parsed.

## File Structure

```
models/
  kling_v3/
    config.json   ← {\"name\": \"Kling v3 Pro\", \"endpoint\": \"fal-ai/kling-video/v3/pro/text-to-video
- /kling-video/v1.6/standard/text-to-video
- /kling-video/v1.5/pro/text-to-video

## Provider Fallbacks

When the primary provider is unavailable, use the fallback chain in [references/higgsfield-fallback.md](references/higgsfield-fallback.md):
1. **Higgsfield MCP** (`mcp_higgsfield_generate_video`) — primary
2. **FAL direct REST API** — fallback when Higgsfield MCP server is down
3. **Alternative providers** (Runway, Pika) — last resort, requires API keys

**Critical signal**: Digest-only results from `mcp_higgsfield_*` tools across 2+ consecutive calls = MCP server down. Do not retry indefinitely.\"}
    prompt.md     ← preprompt + rules + output format
    schema.md     ← API params, types, constraints, JSON examples
  runway_gen4/
    config.json
    prompt.md
    schema.md
```

## Steps

### 1. DB Migration
Add generic columns alongside existing model-specific ones (backward compat):
```sql
ALTER TABLE video_analysis ADD COLUMN model_id TEXT DEFAULT 'kling_v3';
ALTER TABLE video_analysis ADD COLUMN model_payloads TEXT;
ALTER TABLE video_analysis ADD COLUMN job_status TEXT;
ALTER TABLE video_analysis ADD COLUMN job_request_id TEXT;
ALTER TABLE video_analysis ADD COLUMN job_result TEXT;
ALTER TABLE video_analysis ADD COLUMN job_error TEXT;
```
Then copy existing data: `UPDATE video_analysis SET model_id='kling_v3', job_status=kling_status, ...`

### 2. Model Runner Module (`modules/model_runner.py`)
Core functions:
- `list_models()` — scan `models/` dir, read config.json, inject `id` from dir name
- `load_model(model_id)` — return `{config, prompt, schema}` (3 separate values)
- `generate_payload(card_id, model_id)` — LLM call with system=prompt, user={analysis, comments, schema}
- `submit(card_id)` — send payload to Fal.ai via `fal_client.submit(endpoint, arguments)`
- `sync(card_id)` — check Fal.ai job status, fetch result when complete
- `sync_all()` — batch sync active jobs

**Endpoint resolution:** always from `config.json` → `endpoint`. Payload can override with `endpoint` key. No mode-switching logic needed.

### 3. API Routes (`app/models.py`)
Generic routes replacing hardcoded Kling ones:
- `GET /api/models` — list available models
- `GET /api/models/<id>` — get model config + prompt + schema
- `POST /api/models` — create new model (validate JSON config, write 3 files)
- `PUT /api/models/<id>` — update model files (config/prompt/schema)
- `DELETE /api/models/<id>` — remove model
- `POST /api/generate/<card_id>/<model_id>` — async payload generation
- `POST /api/submit/<card_id>` — submit to Fal.ai
- `POST /api/sync/<card_id>` — sync job status
- `GET /api/payload/<card_id>` — get saved payload

### 4. Dashboard UI
- Header: model selector dropdown (loads from `/api/models`)
- Card badges: show `job_status` + `model_id` (with fallback to `kling_status`)
- Detail tab "Generate": model selector + Generate/Submit/Sync buttons + JSON textarea
- "⚙ Models" modal: CRUD interface for model configs (config.json + prompt.md textareas)

### 5. Backward Compat
- Keep old `kling_*` columns in DB, read from `COALESCE(job_status, kling_status)`
- Keep old `app/kling.py` blueprint registered (legacy routes still work)
- Both old and new columns populated during migration

## Pitfalls
- `model_runner.list_models()` must inject `cfg['id'] = dir_name` since config.json doesn't contain id
- **prompt.md and schema.md are SEPARATE** — user explicitly rejected merging them. Both are plain text injected to LLM, not parsed programmatically
- Endpoint resolution in sync/submit must check payload first, then fall back to model config
- Flask requires restart after changes to `model_runner.py` (loaded at import time)
- DB migration: use `COALESCE(job_status, kling_status)` for backward compat reads

## Adding a New Model (via dashboard)
1. Click "⚙ Models"
2. Click "+ New Model"
3. Fill **config.json**: `{\"name\": \"My Model\", \"endpoint\": \"fal-ai/some/model\"}`
4. Write **prompt.md**: system instructions + rules + output format
5. Write **schema.md**: API params, types, constraints, JSON examples
6. Save → model appears in dropdown immediately
