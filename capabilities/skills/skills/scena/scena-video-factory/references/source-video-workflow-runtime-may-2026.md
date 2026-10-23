# Source-video workflow runtime — May 2026

Session learning from implementing the first runtime block of `workflow_video_ai_seedance_agent_spec.md` in `/root/projects/scena-cloudflare`.

## Scope

Class of task: turning Scena workflow guidance into deterministic, DB-traced execution for source-video → target-video regeneration across Telegram and Scena Connect.

This is **not** full generation yet. It covers ingestion, artifact metadata, and initial analysis/planning tools.

## DB pattern

Add a metadata-only artifact table while keeping free-tier constraints:

```sql
CREATE TABLE IF NOT EXISTS workflow_artifacts (
    id TEXT PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    project_id TEXT DEFAULT '',
    workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id),
    workflow_id TEXT DEFAULT '',
    workflow_step_key TEXT DEFAULT '',
    artifact_type TEXT NOT NULL,
    artifact_role TEXT DEFAULT 'metadata',
    name TEXT DEFAULT '',
    mime_type TEXT DEFAULT '',
    file_url TEXT DEFAULT '',
    drive_file_id TEXT DEFAULT '',
    drive_web_view_link TEXT DEFAULT '',
    storage_provider TEXT DEFAULT 'd1',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_run ON workflow_artifacts(workflow_run_id, workflow_step_key, artifact_type);
CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_client ON workflow_artifacts(client_id, project_id, created_at);
```

Keep heavy files on Google Drive (`w.alter`) or Telegram proxy URLs; store only traceable metadata and links in D1.

## Runner additions

Extend `workflow_runner.ts` with:
- `recordWorkflowArtifact(env, input)` — inserts artifact row and appends `workflow_trace_events` event `artifact_recorded`.
- `listWorkflowArtifacts(env, workflowRunId, stepKey?)` — loads artifacts by run/step.
- `WorkflowExecutionContext.artifacts` — include recent artifacts in `executionMd` so the agent sees available source/video/analysis artifacts.

Important: include `workflow_id` in the insert parameters. Tests that capture `params[]` must map indexes accordingly:
- `params[3]` = `workflow_run_id`
- `params[4]` = `workflow_id`
- `params[5]` = `workflow_step_key`
- `params[6]` = `artifact_type`

## Tool additions

Expose tools in `tools.ts` and route them in `agent.ts`:

- `prepare_video_artifacts`
  - input: `source_video_url`, `client_brief`, target info, storage/folder.
  - records `source_video` artifact and `artifact_manifest` artifact.
  - returns `drive_status: pending_sidecar_upload` when `storage=google_drive`.
  - does not generate media or consume credits.

- `analyze_video_source`
  - sends `video_url` + text prompt to OpenRouter video-capable Gemini model.
  - stores `source_analysis` artifact with strict JSON output.
  - must not convert the source video into a final generation prompt.

- `build_modification_plan`
  - converts brief into atomic JSON: `preserve`, `change`, `remove`, `add`, `upgrade`, `constraints`, `risks`, `validation_summary`.
  - stores `modification_plan` artifact.
  - uses source analysis if present but client modifications override source facts.

## Telegram source-video intake pattern

Handle both:
- `message.video`
- `message.document` where `mime_type` starts with `video/`

Create a proxy URL:

```text
https://api.walter-ai.cloud/proxy/media/{file_id}?client={matricule}
```

Save in `clients.notes`:

```json
{
  "pending_source_video_url": "https://api.walter-ai.cloud/proxy/media/...",
  "pending_source_video_mime_type": "video/mp4",
  "source_video_ts": 1234567890
}
```

When caption/text is present, call `handleAgentMessage` with an augmented user prompt containing:

```text
[SOURCE_VIDEO_PROXY_URL]: https://api.walter-ai.cloud/proxy/media/...
⚠️ Utilise cette URL comme source_video_url pour les outils prepare_video_artifacts / analyze_video_source.
⚠️ Workflow source→target: ne saute pas directement au prompt final; prépare les artifacts puis analyse objectivement la source.
```

For a text follow-up like `vas y`, reuse `pending_source_video_url` if fresh (implementation used a 30-minute TTL) and inject the same `[SOURCE_VIDEO_PROXY_URL]` block.

## Tests to keep

Add/keep `tests/video-workflow-runtime.test.mjs` covering:
1. `SCENA_TOOLS` exposes `prepare_video_artifacts`, `analyze_video_source`, `build_modification_plan`.
2. `recordWorkflowArtifact` persists metadata + trace event.
3. `prepare_video_artifacts` records `source_video` + `artifact_manifest` and advances the workflow step.
4. Telegram `message.video` injects `[SOURCE_VIDEO_PROXY_URL]` into the agent prompt and stores `pending_source_video_url`.
5. Telegram text follow-up reuses fresh pending source-video URL.

Run focused bundle:

```bash
node --experimental-strip-types --test \
  tests/video-workflow-runtime.test.mjs \
  tests/workflow-runner.test.mjs \
  tests/video-workflow-catalog.test.mjs \
  tests/video-workflow-seed-script.test.mjs \
  tests/provider-payloads.test.mjs \
  tests/saas-connect.test.mjs \
  tests/telegram-ui.test.mjs \
  tests/worker-regressions.test.mjs
```

Expected result from implementation session: 62/62 passing.

Full `npm test` may still show unrelated portal/vitrine failures from existing HTML tests. Do not attribute those to workflow runtime changes unless `pages/portal`/vitrine files were touched.

## Deployment/migration commands

Create dedicated SQL file like `d1/workflow-artifacts.sql`, then apply:

```bash
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
wrangler d1 execute scena-db --remote --file=d1/workflow-artifacts.sql
```

Verify table:

```bash
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
wrangler d1 execute scena-db --remote --command="PRAGMA table_info(workflow_artifacts);"
```

## Admin Workflow Control Center (May 2026)

When Lucas asks for a complete workflow interface, add a dedicated admin runtime view rather than overloading the workflow-pack editor.

Recommended implementation in `/root/projects/scena-cloudflare`:
- `workers/api/src/workflow_admin.ts` exposes admin-only APIs:
  - `GET /api/admin/workflow-runs` — live run summaries with client/project/workflow, status, current step, step/artifact/event counters.
  - `GET /api/admin/workflow-runs/:run_id` — complete detail: run, workflow, project, steps joined with `workflow_step_runs`, artifacts, trace events, linked image/video jobs.
  - `PUT /api/admin/workflow-runs/:run_id/steps/:step_key/control` — stores per-run `admin_control` inside `workflow_step_runs.input_json` with `prompt_override_md`, `inputs`, and `params_override_json`.
- `workflow_runner.buildWorkflowExecutionMd(...)` must read the current step run's `input_json.admin_control` and inject:
  - `Admin prompt override (authoritative for this run)` when set.
  - `Admin manual inputs (merge into the next tool call)`.
  - default params merged with `params_override_json`.
- `pages/admin/index.html` should expose a `Workflow Control Center` tab with:
  - live run list
  - `Live step timeline`
  - `Live trace`
  - artifacts and linked media jobs
  - per-step `Prompt override`, `Input JSON`, `Params override JSON`
  - detail auto-refresh while a run is selected.

Production verification pattern:
```bash
TOKEN=$(curl -sS -X POST https://api.walter-ai.cloud/api/admin/login \
  -H 'Content-Type: application/json' \
  --data '{"password":"<ADMIN_SECRET>"}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')

curl -sS 'https://api.walter-ai.cloud/api/admin/workflow-runs?client_id=3&limit=5' \
  -H "Authorization: Bearer $TOKEN"

curl -sS 'https://api.walter-ai.cloud/api/admin/workflow-runs/<run_id>' \
  -H "Authorization: Bearer $TOKEN"

curl -L -sS https://admin-scena.walter-ai.cloud | grep -E 'Workflow Control Center|loadWorkflowRuns|saveWorkflowStepControl'
```

Regression test to keep: `tests/workflow-control-center.test.mjs`.

### Live D1 schema pitfall
Production `image_jobs` uses `input_prompt`, not `prompt`. Detail APIs that select linked image jobs must query `input_prompt` directly, otherwise prod returns:
```text
D1_ERROR: no such column: prompt
```

## Pitfalls

- Telegram video files are not photos. Do not rely on `imageUrl`/`pending_proxy_url`; add a separate `pending_source_video_url` path.
- Text follow-up (`vas y`) after a source video must reuse the pending source video. Otherwise the agent sees only `vas y` and cannot call `prepare_video_artifacts` with a URL.
- Keep source-video workflow separate from the regular photo → video picker. A source video is a reference for deterministic regeneration, not just an image animation request.
- `prepare_video_artifacts` should be sync and no-credit. Generation remains gated until later validation steps.
- For OpenRouter video input, only video-capable Gemini-family routes are reliable; do not assume OpenAI/Anthropic on OpenRouter accept video.
