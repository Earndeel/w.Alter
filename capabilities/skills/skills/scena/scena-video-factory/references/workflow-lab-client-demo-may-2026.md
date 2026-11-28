# Scena Workflow Lab + Client Demo (May 2026)

Use this when adding or repairing Scena's SaaS-facing demonstration surface or deep workflow/payload editor.

## Goal
Scena needs two distinct surfaces:
1. **Client demo page** — shows SaaS prospects what the engine can do from their own UI: one brief, source video URL, image/video inputs, then Scena handles analysis, character sheets, storyboard, clip segmentation, provider payload compilation, async generation, QA, and webhooks.
2. **Workflow Lab admin/operator page** — lets operators inspect and tune each workflow step in depth: preprompt, manual inputs, params, provider/model overrides, and final Seedance payload preview.

Keep these separate. The demo sells capability; the Lab is the operator cockpit. Mixing both makes the client-facing page look like a machine room, which is charming only to engineers.

## Files/patterns from the implementation
- Client demo: `pages/portal/demo.html`
  - Must mention/cover: `Scena Demo Studio`, `source_video_url`, `brief`, `/api/saas/pipeline`, `timeline-demo`, `character sheet`, `storyboard`, `Seedance`, `X-Scena-Demo-Mode`.
  - Demo can run locally in simulation mode when no SaaS API key is provided.
  - If an API key is present, it calls `POST https://api.walter-ai.cloud/api/saas/pipeline` with `Authorization: Bearer <key>`.
- Operator Workflow Lab: `pages/admin/operator.html`
  - Must retain the minimal first-screen contract: `id="startCard"`, `briefInput`, `sourceUpload`, `uploadPreview`, one `Démarrer le workflow` button, compact progress rail.
  - Must expose deeper controls outside the start card: `promptOverride`, `modelProviderOverride`, `modelIdOverride`, `manualInputs`, `paramsOverride`, `previewSeedancePayload`, `seedancePayloadPreview`.
  - Must preserve the exact Drive workflow chain and copy: `source video → objective source analysis → client modification plan` and the 16 step keys.
- Worker API: `workers/api/src/workflow_admin.ts`
  - `GET /api/admin/workflow-lab/config` returns supported models and `PROVIDER_PAYLOAD_SCHEMAS`.
  - `POST /api/admin/workflow-runs/:runId/steps/:stepKey/payload-preview` returns a sanitized provider payload preview.
  - Existing `PUT /api/admin/workflow-runs/:runId/steps/:stepKey/control` already persists per-run overrides in `workflow_step_runs.input_json.admin_control`.

## Seedance payload preview rules
For Kie Seedance, build the preview through `buildKieSeedanceVideoInput(...)` from `provider_payloads.ts` instead of hand-assembling fields.

Required output shape:
```json
{
  "ok": true,
  "provider": "kie",
  "model_id": "bytedance/seedance-2-fast",
  "step_key": "compile_provider_payloads",
  "payload": {
    "model": "bytedance/seedance-2-fast",
    "input": {
      "prompt": "...",
      "resolution": "720p",
      "aspect_ratio": "9:16",
      "duration": 5,
      "generate_audio": false,
      "web_search": false
    }
  },
  "schema": { "...": "from PROVIDER_PAYLOAD_SCHEMAS" },
  "diagnostics": ["Seedance constraints applied: ..."]
}
```

Sanitization expectations:
- `duration`: clamp to `5..15`.
- `aspect_ratio`: normalize to `16:9`, `9:16`, `1:1`, `4:3`, `3:4`.
- `resolution`: normalize to `720p` or `1080p`.
- `generate_audio`, `web_search`, `return_last_frame`: parse boolean-like strings.
- `first_frame_url`/`last_frame_url` mode is mutually exclusive with multimodal references.
- Prompt preview should combine step/preprompt override + manual/body prompt fields + product name where available.

## Tests to add/keep
Use test-first for this class of change.

Recommended regression bundle:
```bash
node --experimental-strip-types --test \
  tests/client-demo-workflow-lab.test.mjs \
  tests/workflow-control-center.test.mjs \
  tests/operator-workflow-ui.test.mjs \
  tests/pipeline-runner.test.mjs \
  tests/saas-connect.test.mjs

npm test
```

`tests/client-demo-workflow-lab.test.mjs` should assert:
- client demo page includes the SaaS pipeline contract and visible staged workflow language;
- operator Lab includes model/preprompt/payload controls;
- payload preview endpoint returns sanitized Kie Seedance payload + diagnostics.

Existing `operator-workflow-ui.test.mjs` has important guardrails. If you refactor `operator.html`, preserve:
- `id="startCard"` around the minimal start section;
- the literal source workflow phrase;
- all 16 Drive workflow step keys;
- no old fake 6-step pipeline functions.

## HTML-writing pitfall
For these large HTML files, write via Python/Node direct file I/O or heredoc, then verify scripts parse. Avoid read-modify-write using line-numbered tool output.

Script parse check:
```bash
node - <<'NODE'
const fs=require('fs');
for (const file of ['pages/portal/demo.html','pages/admin/operator.html']) {
  const html=fs.readFileSync(file,'utf8');
  const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  for (const js of scripts) new Function(js);
  console.log(`${file}: ${scripts.length} inline script(s) parse ok`);
}
NODE
```

## Deploy note
Do not deploy Pages/Worker silently. After tests pass, ask/await explicit go-ahead before production deploy. Use the correct Pages project names from the main skill (`scena-admin`, portal project as appropriate), not the custom domain names.
