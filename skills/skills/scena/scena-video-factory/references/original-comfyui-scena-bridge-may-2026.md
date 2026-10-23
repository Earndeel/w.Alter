# Original ComfyUI Scena bridge — May 2026

Use when Lucas asks to put a Scena workflow into the **real/original ComfyUI interface**, not just an admin LiteGraph mock.

## Durable pattern

- Keep heavy generation in Scena/Kie/Fal/OpenRouter/Drive APIs; ComfyUI is the visual editor/control surface.
- Add a ComfyUI custom node package under:
  - `/root/comfy/ComfyUI/custom_nodes/scena_workflow_nodes/__init__.py`
  - `/root/comfy/ComfyUI/custom_nodes/scena_workflow_nodes/web/scena_workflow_loader.js`
- Export both formats:
  - editor workflow: `/root/comfy/ComfyUI/user/default/workflows/scena-source-video-to-target-regeneration-comfyui.json`
  - API workflow: `/root/comfy/ComfyUI/user/default/workflows/scena-source-video-to-target-regeneration-api.json`
  - also serve copies from the custom node `web/` dir so the frontend loader can fetch them through `/extensions/scena_workflow_nodes/...`.

## Node classes used

- `ScenaRunControl`
- `ScenaManualInputs`
- `ScenaPreprompt`
- `ScenaWorkflowStep`
- `ScenaProviderAPI`
- `ScenaGeneratedOutput`

Expose them via `NODE_CLASS_MAPPINGS`, `NODE_DISPLAY_NAME_MAPPINGS`, and `WEB_DIRECTORY = "./web"`.

## Frontend loader pattern

Create a ComfyUI frontend extension importing:

```js
import { app } from "../../scripts/app.js";
```

Register `app.registerExtension({ name: "Scena.WorkflowLoader", setup() { ... } })` and add:

- a fixed button: `Load Scena Workflow`
- an auto-load query param such as `?scena=1`
- loader fetch path: `/extensions/scena_workflow_nodes/scena-source-video-to-target-regeneration-comfyui.json`
- `await app.loadGraphData(workflow)` then mark canvas dirty.

## Important pitfall: fallback links

Scena fallback routes can create cycles if represented as executable ComfyUI links between step nodes. Keep fallback metadata visible in `ScenaWorkflowStep.fallback_workflow_step_key`, but do not connect fallback routes as execution dependencies unless the graph is guaranteed acyclic. Otherwise `/prompt` returns `dependency_cycle` node errors.

## Verification

1. Restart ComfyUI after adding nodes: `systemctl restart comfyui.service`.
2. Confirm custom nodes are registered:
   - `GET http://127.0.0.1:8188/object_info/ScenaWorkflowStep`
3. Confirm extension assets are served:
   - `GET http://127.0.0.1:8188/extensions/scena_workflow_nodes/scena_workflow_loader.js`
   - `GET http://127.0.0.1:8188/extensions/scena_workflow_nodes/scena-source-video-to-target-regeneration-comfyui.json`
4. Validate API workflow by POSTing `/prompt`; require `node_errors == {}` and successful history.
5. For UI verification, do not rely only on a screenshot of the splash logo. Extract DOM text after load and verify strings like `Load Scena Workflow`, `Scena workflow loaded`, `Scena Run Control`, and multiple Scena step titles.

## UX preference from Lucas

If Lucas says “ComfyUI original”, use the actual ComfyUI frontend with custom nodes and loader button/autoload URL. A Comfy-like admin UI or standalone LiteGraph imitation is not enough.

### Preferred operator workflow after Lucas feedback

Do **not** expose the full 16-step internal workflow as the default UX. Lucas wants a simple human-review flow:

1. Only two visible entry inputs at the start:
   - `1. Prompt — ce que je veux` (`ScenaClientBrief`)
   - `2. Inputs — fichiers / références` (`ScenaSourceInputs`)
2. Then generate/edit/check in phases:
   - draft brief + preprompts
   - REVIEW 1: preprompts
   - generate reference image prompts
   - REVIEW 2: reference prompts
   - generate reference images/assets
   - REVIEW 3: reference assets
   - build final video prompt/package
   - REVIEW 4: before video generation
   - only then submit `API • VIDEO GENERATION — Kie Seedance`
3. Default autoload should open the simple workflow: `https://comfy.walter-ai.cloud/?workflow=simple`.
4. Keep the full technical workflow available behind `?workflow=full` or a secondary `Load Scena Workflow` button, but do not make it the primary route.
5. If Lucas says the graph is unreadable or asks for a clean interface, stop iterating on ComfyUI/LiteGraph. Build/use the standalone operator UI instead: prompt + uploads on the left, stage/review pipeline in the center, editable result panel on the right.

Standalone clean operator UI:
- Source: `/root/projects/scena-cloudflare/pages/admin/operator.html`
- Production URL: `https://admin-scena.walter-ai.cloud/operator`
- Tests: `/root/projects/scena-cloudflare/tests/operator-workflow-ui.test.mjs`
- UX: no LiteGraph, no node graph; stages are `preprompts`, `asset-prompts`, `reference-assets`, `video-package`, `final-video`; video stays blocked until `video-package` is approved.
- Source storage: VM temporary storage first, Google Drive only as fallback/archive, never R2 for free-tier operator staging. VM temp public URL: `https://temp-scena.walter-ai.cloud`; local service: `scena-temp-storage.service` on `127.0.0.1:8799`; root: `/var/lib/scena-temp-storage`; TTL: 24h; hourly cleanup timer: `scena-temp-storage-cleanup.timer`; service code: `/opt/scena-temp-storage/server.py`.
- VM upload route: `POST /api/admin/operator/vm-upload` with admin auth + multipart `file`; Worker forwards to the VM service using secrets `SCENA_TEMP_STORAGE_URL` and `SCENA_TEMP_STORAGE_TOKEN`; service auth token is also in `/etc/scena-temp-storage.env` and `/root/.scena-temp-storage-token`. The operator video submit prefers `vmRefs[0]`, then `driveRefs[0]`, then manual refs.
- Drive archive/fallback route: `POST /api/admin/operator/drive-upload` with admin auth + multipart `file`; Worker secrets required: `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, `GOOGLE_DRIVE_REFRESH_TOKEN`, `GOOGLE_DRIVE_OPERATOR_FOLDER_ID`. Current folder: `Scena Operator Source Uploads` under `w.alter`, URL `https://drive.google.com/drive/folders/1A8xvmShe2exl1Nu3FvsAcbkO54FWF9B0`. The route uploads to Drive, sets `anyone reader` permission, returns `download_url = https://drive.google.com/uc?export=download&id=<fileId>`.
- Backend tests: `/root/projects/scena-cloudflare/tests/operator-vm-upload.test.mjs`, `/root/projects/scena-cloudflare/tests/operator-drive-upload.test.mjs`, and `/root/projects/scena-cloudflare/tests/operator-video-submit.test.mjs`.

Installed simple workflow artifacts:
- `/root/comfy/ComfyUI/user/default/workflows/scena-human-review-video-workflow-comfyui.json`
- `/root/comfy/ComfyUI/user/default/workflows/scena-human-review-video-workflow-api.json`
- web copies under `/root/comfy/ComfyUI/custom_nodes/scena_workflow_nodes/web/`

Extra custom nodes added for this UX:
- `ScenaClientBrief`
- `ScenaSourceInputs`
- `ScenaHumanReviewGate`