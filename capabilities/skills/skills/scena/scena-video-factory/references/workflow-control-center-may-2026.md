# Workflow Control Center — May 2026

Session learning from adding a live admin interface for Scena deterministic workflow runs in `/root/projects/scena-cloudflare`.

## Scope

Class of work: when Scena has DB-backed workflow execution (`workflow_runs`, `workflow_step_runs`, `workflow_artifacts`, `workflow_trace_events`) and Lucas asks for an operator UI to see every step live and control prompts/inputs per step.

## Backend API pattern

Add a focused Worker module, e.g. `workers/api/src/workflow_admin.ts`, and route it from `handleAdminAPI` after auth:

- `GET /api/admin/workflow-runs`
  - filters: `client_id`, `workflow_id`, `status`, `limit`
  - returns run summaries with joins against `clients`, `workflow_packs`, `tenant_projects`
  - includes counters via subqueries: `step_count`, `completed_step_count`, `artifact_count`, `event_count`

- `GET /api/admin/workflow-runs/:runId`
  - returns a full run detail payload:
    - `run`, `client`, `project`, `workflow`
    - ordered `steps` with joined `workflow_step_runs`
    - `artifacts`
    - `trace_events`
    - linked media jobs: `video_jobs`, `image_jobs`
  - normalize each step with:
    - `admin_control.prompt_override_md`
    - `admin_control.inputs`
    - `admin_control.params_override_json`
    - `admin_control.model_provider_override`
    - `admin_control.model_id_override`
    - `effective_instruction_md`
    - `effective_model_provider`
    - `effective_model_id`
    - `effective_params_json`

- `PUT /api/admin/workflow-runs/:runId/steps/:stepKey/control`
  - stores per-run step controls inside `workflow_step_runs.input_json.admin_control`
  - preserves existing `input_json` fields
  - writes a `workflow_trace_events` event like `admin_step_control_updated`

- Optional: `PUT /api/admin/workflow-runs/:runId/control`
  - guarded operator status/current-step control for pause/resume/advance style actions.

## Runner integration

`workflow_runner.ts` should read `workflow_step_runs.input_json.admin_control` for the current step and inject it into `executionMd`:

- `Admin prompt override (authoritative for this run)` replaces the static `workflow_steps.instruction_md` for this run only.
- `Admin manual inputs` are shown explicitly and should be merged into the next tool call.
- `params_override_json` should merge over `workflow_steps.params_json` when showing authoritative step params.
- `model_provider_override` and `model_id_override` should override `workflow_steps.model_provider/model_id`; show the effective provider/model in `executionMd` as `Model selected for this step` so the operator sees exactly which model will be called.

This gives Lucas a live way to steer prompts, models, and inputs without editing the global workflow pack.

## Admin UI pattern

Patch `pages/admin/index.html` with a `Workflow Control Center` tab rather than replacing the existing Production Chain:

- left pane: live run list
- right pane: selected run detail
- sections:
  - `Live step timeline`
  - `Prompt override + Input JSON`
  - `Artifacts`
  - `Live trace`
  - `Media jobs`
- keep an auto-refresh like:

```js
setInterval(function(){if(_selectedWorkflowRunId) loadWorkflowRunDetail(true);},5000);
```

Add functions:
- `loadWorkflowRuns()`
- `openWorkflowRun(id)`
- `loadWorkflowRunDetail(silent)`
- `renderWorkflowRunDetail()`
- `editWorkflowStepControl(stepKey)`
- `saveWorkflowStepControl()`

### Dedicated Operator Studio pass

If Lucas says he wanted a **dedicated page** with a real interface where he can upload images/videos, control pre-prompts, and see text/image generations at each step, do not answer only with the ComfyUI/LiteGraph admin tab. Use the additive `pages/admin/operator.html` route as a clean operator UI:

- expose it from `pages/admin/index.html` with a direct `Operator Studio` nav entry and a workflow-top button (`window.location.href='operator.html'`);
- keep the two basic inputs at the top: main prompt + files/reference URLs;
- support source uploads through existing admin endpoints:
  - `POST /api/admin/operator/vm-upload` for temporary VM public URLs;
  - `POST /api/admin/operator/drive-upload` for Google Drive archive/source URLs;
- keep video submission blocked behind final human approval via `POST /api/admin/operator/video` with `approved:true` only after the final package is validated;
- connect live workflow runs, not just local/fake stages:
  - `loadWorkflowRuns()` should list runs from `GET /api/admin/workflow-runs`;
  - `openWorkflowRun(runId)` should fetch `GET /api/admin/workflow-runs/:runId`;
  - group `workflow_step_runs.output_json`, `workflow_artifacts`, `media_jobs.image`, `media_jobs.video`, and trace events by `workflow_step_key`;
  - render `Preprompt Control`, `Manual Inputs`, `Generated Text`, and `Generated Outputs` per step;
  - `saveLiveStepControl(runId, stepKey)` should persist per-run prompt/input overrides through `PUT /api/admin/workflow-runs/:runId/steps/:stepKey/control`.
- keep the dedicated page free of `LiteGraph` / `LGraphCanvas`; Lucas asked for a clean operator page, not another node graph.
- verify static deploy on both hash URL and `https://admin-scena.walter-ai.cloud/operator.html` for markers: `Scena Operator Studio`, `Prompt + uploads + Preprompt Control`, `Generated Outputs`, `openWorkflowRun`, `saveLiveStepControl`, `workflow-output-preview`.

Regression coverage: extend `tests/operator-workflow-ui.test.mjs` to assert the dedicated page, admin nav link, live run detail loading, preprompt/input save route, and generated output previews. Keep upload/video endpoint tests (`operator-vm-upload`, `operator-drive-upload`, `operator-video-submit`) green.

### Exact Drive Workflow Operator pass

If Lucas says the operator UI is overloaded, fake, or not following the Drive `.md`, stop adding explanatory cards. Retrieve/read `video-source-to-target-regeneration.md` from Google Drive and make `pages/admin/operator.html` follow that exact workflow:

- Use the exact workflow id `video-source-to-target-regeneration-v1`.
- Use the exact 16 step keys from the Drive document: `ingest_inputs`, `validate_source_media`, `prepare_media_artifacts`, `source_objective_analysis`, `scene_level_refinement`, `modification_plan`, `source_to_target_mapping`, `target_entities_and_sheets`, `target_timeline`, `generation_clip_segmentation`, `storyboard_and_reference_plan`, `compile_provider_payloads`, `qa_generation_package`, `await_client_validation`, `submit_generation_after_validation`, `export_project_package`.
- UI rule: first screen must be minimal: one brief textarea, one upload input, one start button, compact progress rail. No visible storage explanation, no model catalog text, no generated fake stages, no `Stockage preprompts & modèles` block.
- Do not use the fake local 6-step generator (`generatePreprompts`, `generateAssetPrompts`, `generateReferenceAssets`, `generateVideoPackage`) as the primary process.
- Add/use `POST /api/admin/workflow-runs/start` to create a real D1 `workflow_runs` row and 16 `workflow_step_runs` rows from the DB workflow pack. The first step input should include `source_video_url`, `client_brief`, Drive doc id `1kpG13Z_W20o-EY5n5r9nFAEI0hkjiGrL`, the core rule, truth hierarchy, and Google Drive `w.alter` artifact policy.
- Operator start flow: upload source to `/api/admin/operator/vm-upload` if needed, then call `/api/admin/workflow-runs/start`, then load `/api/admin/workflow-runs/:runId`.
- Keep per-step control available but collapsed under a compact `Contrôle étape` details element.
- Regression tests: assert exact 16 step keys, no fake 6-step strings, no storage explainer, start route `/api/admin/workflow-runs/start`, and backend start endpoint creates 16 step runs.

### Guided Operator Wizard pass

If Lucas says the dedicated operator UI is still not user friendly enough and he wants to "just put my prompt, upload inputs, then advance step by step", make `pages/admin/operator.html` default to a guided wizard:

- Top/default card must be `Mode guidé` with one big textarea `id="guidedPrompt"`, one file upload `id="guidedAssetUpload"`, visible `guidedInputPreview`, and the exact plain flow label `Prompt → Inputs → Analyse → Plan → Images → Vidéo`.
- **Strict first-screen rule from Lucas:** the initial card must show ONLY the text window, the input upload, preview, and `Commencer pas à pas`. Do not show client, format, duration, source URLs, quality constraints, VM/Drive buttons, live runs, mode expert, storage statuses, or any technical setting there. Format/duration should be written in the prompt and can be inferred silently.
- Keep compatibility IDs used by existing logic/tests in a hidden technical map, not visible in the start card: `creativePrompt`, `assetUpload`, `uploadPreview`, `clientSelect`, `aspectRatio`, `duration`, `referenceUrls`, `qualityConstraints`, `vmUploadStatus`, `driveUploadStatus`.
- First screen wording should be simple: `Décris ce que tu veux faire`; CTA: `Commencer pas à pas`.
- Add `guidedStepPanel`, `wizard-progress`, and visible copy `Ce qu’on fait maintenant`.
- Implement these JS functions as wrappers around the existing operator functions:
  - `startGuidedWorkflow()` copies guided prompt into classic state, generates preprompts, opens step 1 immediately.
  - `startGuidedWorkflow()` must **not await video/file upload before advancing**. Large video uploads make the button look dead. If uploading inputs automatically, call a background helper such as `kickoffGuidedInputUpload()` only after `goToGuidedStep(1)`.
  - `goToGuidedStep(step)` updates the wizard and existing result tabs.
  - `guidedStepNext()` validates current step and calls the next existing generator (`generateAssetPrompts`, `generateReferenceAssets`, `generateVideoPackage`, then `submitVideoGeneration`).
  - `renderGuidedStep()` shows the current editable text or generated output cards.
- Keep existing backend integrations intact: VM upload, Drive upload, live runs, per-step control, final `POST /api/admin/operator/video` blocked until `video-package` approval.
- Keep the expert/admin entry available via `index.html#workflows`, but default `operator.html` should no longer look like a technical 3-column control room.
- Regression test: extend `tests/operator-workflow-ui.test.mjs` with markers for `Mode guidé`, `guidedStartCard`, `guidedPrompt`, `guidedAssetUpload`, `guidedStepPanel`, `wizard-progress`, `startGuidedWorkflow`, `goToGuidedStep`, `guidedStepNext`, `renderGuidedStep`, and `Valider et continuer`.
- Deployment verification markers on both hash and custom domain: `Mode guidé`, `Décris ce que tu veux faire`, `guidedStartCard`, `guidedPrompt`, `guidedAssetUpload`, `wizard-progress`, `Ce qu’on fait maintenant`, `Valider et continuer`, `Generated Outputs`.

### Lucas-friendly simplification pass

If Lucas says the Workflow Control Center is confusing, keep the same backend/API but make the admin tab operator-first:

- Add a visible `Mode simple` guide at the top with exactly three cards: `1. Lancer`, `2. Suivre`, `3. Modifier`.
- Rename the run list to `Derniers workflows` instead of technical `Runs live`.
- In the selected run detail, show `Ce qui se passe maintenant` before expert sections, with plain-French `Statut`, `Étape actuelle`, `Progression`, and `Prochaine action`.
- Keep existing expert anchors/strings (`Live step timeline`, `Live trace`, `Prompt override`, `Input JSON`) so current tests and operator affordances still work.
- Do not add a fake launch button if backend launch is not implemented; explain that launching happens from Telegram or Scena Connect and the run then appears in the admin.

### Node-studio / ComfyUI-style pass

If Lucas says he wants a **real interface**, not a simplified dashboard, use the Node Studio pattern:

- Same backend routes are enough: `GET /api/admin/workflow-runs/:runId` already returns steps, `effective_instruction_md`, `admin_control`, artifacts, trace, image jobs and video jobs grouped by `workflow_step_key`.
- Replace the selected-run detail with a ComfyUI-style canvas:
  - `workflow-node-canvas`: grid of node cards, one per workflow step.
  - `workflow-node-inspector`: sticky panel for the selected node.
  - `collectStepMedia(stepKey)`: groups `media_jobs.image`, `media_jobs.video`, `artifacts`, and `trace_events` by `workflow_step_key` / `step_key`.
- Each node should show status, tool/model, badges for `preprompt override`, `manual inputs`, `params override`, and a thumbnail strip of generated images/videos for that step.
- Inspector sections:
  - `Manual Inputs`: editable `Input JSON` and `Params override JSON` saved through `saveWorkflowStepControl()`.
  - `Preprompt Editor`: read-only source `workflow_steps.instruction_md` plus editable `Prompt override` for this run.
  - `Generated Outputs`: gallery with `<img>` previews for image jobs/artifacts and `<video controls>` previews for video jobs/artifacts.
  - `Node JSON` + `Live trace`: read-only debug context.
- Keep it per-run by default. Do not mutate global `workflow_steps.instruction_md` unless Lucas explicitly asks for global workflow-pack editing.
- Regression test strings worth keeping for the lightweight fake-node version: `Comfy-style Node Graph`, `workflow-node-canvas`, `workflow-node-inspector`, `Manual Inputs`, `Preprompt Editor`, `Generated Outputs`, `renderWorkflowNodeGraph(`, `openWorkflowNode(`, `collectStepMedia(`, `workflow-output-gallery`, `<img class="workflow-output-preview"`, `<video class="workflow-output-preview"`.

### Real ComfyUI/LiteGraph integration pass

If Lucas explicitly says to use **ComfyUI** rather than a custom fake node UI, embed LiteGraph locally in `pages/admin` and build a real canvas:

- Vendor assets locally under `pages/admin/vendor/litegraph/` (avoid CDN fragility):
  - `litegraph.min.js`
  - `litegraph.css`
- Include them in `pages/admin/index.html` before the main admin script.
- UI labels should make it explicit: `ComfyUI Workflow Studio` / `ComfyUI graph canvas`.
- Register Scena node types with LiteGraph:
  - `Scena/RunControl`
  - `Scena/ManualInputs`
  - `Scena/Preprompt`
  - `Scena/WorkflowStep`
  - `Scena/ProviderAPI`
  - `Scena/GeneratedOutput`
- Build the full workflow graph from the run detail and workflow pack detail:
  - `GET /api/admin/workflow-runs/:runId`
  - `GET /api/admin/workflow-packs/:workflowId`
- Required JS functions:
  - `registerScenaComfyNodes()`
  - `ensureScenaComfyCanvas()` uses `new LGraph()` and `new LGraphCanvas(...)`
  - `buildScenaComfyWorkflow()` creates nodes for every step: Preprompt → Manual Inputs → Workflow Step → Provider/API → Generated Output.
  - `connectScenaComfyNodes()` wires normal next-step flow and fallback links.
  - `serializeScenaComfyApiWorkflow()` exports an API-style JSON object with `class_type`, `inputs`, `_meta`, and node `properties`.
  - `loadWorkflowPackDefinition()` loads global pack steps/bindings for full graph/API connection context.
- Inspector sections should include:
  - `Manual Inputs`
  - `Preprompt Editor`
  - `API Connections` (tool, provider, model, inferred Scena endpoint, model doc)
  - `Generated Outputs`
  - `Node JSON`
  - `Live trace`
- Keep all mutations per-run via `saveWorkflowStepControl()`; do **not** mutate global workflow pack steps unless Lucas explicitly asks for global pack editing.
- Test command stayed green in the implementation run: targeted `workflow-control-center.test.mjs` and regression bundle `78/78`.
- Deployment verification: fetch both hash URL and custom domain and assert strings: `ComfyUI Workflow Studio`, `vendor/litegraph/litegraph.min.js`, `new LGraph(`, `new LGraphCanvas(`, `LiteGraph.registerNodeType('Scena/ManualInputs'`, `buildScenaComfyWorkflow(`, `connectScenaComfyNodes(`, `serializeScenaComfyApiWorkflow(`, `API Connections`, `Generated Outputs`.

### Original ComfyUI integration pass

If Lucas asks to put it in **ComfyUI original**, do not stop at the admin LiteGraph bridge. Use the actual ComfyUI frontend with a custom node package, frontend extension, loader button, and autoload URL. The durable recipe and verification checklist are in `references/original-comfyui-scena-bridge-may-2026.md`.

Key pitfall: Scena fallback routes can create ComfyUI dependency cycles if represented as executable links. Keep fallback metadata visible on the step node, but omit fallback execution links unless guaranteed acyclic.

## Tests to add

Create a targeted test file such as `tests/workflow-control-center.test.mjs` covering:

1. run list endpoint returns summaries with step/artifact counters
2. run detail endpoint returns steps, trace, artifacts, media jobs, prompt overrides, inputs
3. step control endpoint stores prompt overrides and manual input JSON in `workflow_step_runs.input_json.admin_control`
4. workflow execution prompt includes admin prompt/input/params overrides
5. admin dashboard exposes the Workflow Control Center strings/functions

Focused command:

```bash
node --experimental-strip-types --test tests/workflow-control-center.test.mjs
```

Regression bundle:

```bash
node --experimental-strip-types --test \
  tests/workflow-control-center.test.mjs \
  tests/video-workflow-runtime.test.mjs \
  tests/workflow-runner.test.mjs \
  tests/workflow-library.test.mjs \
  tests/video-workflow-catalog.test.mjs \
  tests/video-workflow-seed-script.test.mjs \
  tests/provider-payloads.test.mjs \
  tests/saas-connect.test.mjs \
  tests/telegram-ui.test.mjs \
  tests/worker-regressions.test.mjs \
  tests/admin-dashboard-auth.test.mjs
```

Expected from this implementation run: targeted workflow/admin bundle passed 78/78. Full `npm test` can still show unrelated portal/vitrine failures when `pages/portal` is already out of sync.

## Deployment verification

After deploy, verify with the real admin login flow and API, not just static tests:

```bash
token=$(curl -sS -X POST 'https://api.walter-ai.cloud/api/admin/login' \
  -H 'Content-Type: application/json' \
  --data '{"password":"..."}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')

curl -sS 'https://api.walter-ai.cloud/api/admin/workflow-runs?client_id=3&limit=5' \
  -H "Authorization: Bearer $token"

run=$(curl -sS 'https://api.walter-ai.cloud/api/admin/workflow-runs?client_id=3&limit=1' \
  -H "Authorization: Bearer $token" | python3 -c 'import sys,json; print((json.load(sys.stdin).get("runs") or [{}])[0].get("id",""))')

curl -sS "https://api.walter-ai.cloud/api/admin/workflow-runs/$run" \
  -H "Authorization: Bearer $token"
```

Also verify the deployed admin HTML contains the new UI:

```bash
curl -L -sS https://admin-scena.walter-ai.cloud | grep -E 'Workflow Control Center|loadWorkflowRuns'
```

## Pitfalls

- Production D1 schema can drift from local tests. In this session, `image_jobs` used `input_prompt`, not `prompt`; selecting `prompt AS input_prompt` caused prod detail endpoint 500. Prefer confirmed prod columns or audit with `PRAGMA table_info(image_jobs)` before querying new admin endpoints.
- Do not store prompt overrides on `workflow_steps` if the operator wants per-run control. Store them on `workflow_step_runs.input_json.admin_control` so the global workflow remains stable.
- Avoid replacing existing video/job tabs. Add the Workflow Control Center as an additive admin view so current Scena Telegram and SaaS flows remain intact.
- After deploying the Worker, test both list and detail endpoints. A list endpoint can pass while detail fails due to a linked table column mismatch.
