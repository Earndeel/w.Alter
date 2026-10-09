# Autonomous Media-Agent Integration Audit

Use this reference when a product claims that an agent can plan, generate, inspect, correct, assemble, and deliver media autonomously. Treat it as a runtime capability audit, not a documentation review.

## Evidence ladder

For every claimed capability, collect evidence in this order:

1. **Model surface** — the tool schema is actually sent to the model in the relevant channel/session.
2. **Dispatch** — the selected tool name reaches a concrete handler with validated arguments.
3. **Runtime** — the handler can reach a process/container/service that performs the operation.
4. **Artifact flow** — canonical input/output URLs, metadata, tenant/project IDs, and step IDs are persisted.
5. **Async resumption** — provider completion resumes the workflow rather than merely updating a job row.
6. **Decision gate** — QA output changes control flow: pass, targeted correction, human review, or bounded failure.
7. **Release gate** — delivery cannot happen before the required decision is recorded.
8. **Behavior test** — a real or deterministic fixture proves the complete path, not merely a prompt or function name.

Classify each item as:

- **Proven** — runtime path and behavior test exist.
- **Partial** — planning/schema exists, but execution or control-flow evidence is incomplete.
- **Absent in audited snapshot** — no reachable runtime path was found; re-check current code before repeating this conclusion.

## Dated Scena snapshot — 2026-07-27

Scope: local checkout `/root/projects/scena-cloudflare` plus public health probes. This is a dated implementation snapshot, not a permanent product limitation; re-run the searches and tests before citing it later.

### Proven or materially implemented

- ReAct loop with bounded iterations and tool-result observation: `workers/api/src/agent.ts:141-372`.
- Separate read-only planner invoked after Luna has collected a structured brief: `workers/api/src/agent.ts:193-217` and `678-724`.
- Explicit approval, workflow-order, async-job, fallback, and client-regeneration transitions: `workers/api/src/workflow_runner.ts:787-907` and `996-1132`.
- Planning for independent provider-compatible clips: `workers/api/src/builtin_video_workflows.ts:381-412`.
- Targeted audit run: 44/45 tests passed across ReAct, workflow runner, video workflow runtime, and pipeline runner. The single failure was an unrelated stale model-catalog expectation, so it did not invalidate the media-agent findings.
- Public `/health` and `/ping` returned HTTP 200 during the audit. This proved liveness, not parity between the dirty local checkout and the deployed Worker.

### Partial paths that require re-verification or completion

- The SaaS pipeline contains a rich QA prompt, but the audited `stepQaValidation` set `videoUrl` to an empty string, making the visual-analysis branch unreachable and falling back to basic job-presence checks: `workers/api/src/pipeline_runner.ts:859-909`.
- The workflow’s final control used `validate_media`, whose audited handler performed URL/header/size checks and did not decode the media, verify ratio/duration, or inspect visual/audio/brief compliance: `workers/api/src/agent.ts:967-1045`.
- Provider completion advanced workflow state, then delivered the provider output to Telegram directly; no audited callback path re-invoked the agent for final visual QA before that delivery: `workers/api/src/index.ts:2610-2633`.
- The workflow planned clip segmentation but had no audited assembly tool for concat, transitions, subtitles, music, logo overlays, or master export. Search model schemas, dispatcher cases, handlers, package dependencies, sidecar scripts, and deployment config before declaring this still true.
- `prepare_video_artifacts` recorded a source artifact and a metadata manifest with a pending-sidecar marker; it did not itself create timecode footage, extracted frames, or contact sheets in the audited snapshot: `workers/api/src/agent.ts:1116-1173`.

## Media-worker / sidecar contract

For an edge agent that cannot spawn FFmpeg, expose one authenticated asynchronous media tool backed by a dedicated worker. Prefer a single extensible `render_media_timeline` contract over a flat family of narrow tools.

### Request

- `tenant_id`, `project_id`, `workflow_run_id`, `workflow_step_key`
- caller-generated `idempotency_key`
- signed or private input artifact references with expected hashes and MIME types
- canonical timeline JSON: ordered clips, trims, speed, crop/scale, transition type/duration
- overlay tracks: logo asset, anchor, safe margins, start/end times, opacity
- subtitle track: SRT/ASS or word timings, language, style, safe rectangle
- audio tracks: narration, licensed music, gains, fades, ducking/sidechain policy
- output profile: width, height, fps, codec, pixel format, audio codec/rate, duration policy, faststart
- QA policy: technical checks, visual sampling cadence, script/ASR check, thresholds, maximum correction attempts

### Response and lifecycle

- Immediate response: `job_id`, accepted normalized spec, estimated work class, and status URL.
- Statuses: `queued → running → rendered → qa_running → passed | needs_revision | failed`.
- Persist the rendered master as a new immutable artifact; never overwrite provider originals.
- Sign callbacks with HMAC and include monotonic attempt/version fields.
- Make callback handling idempotent and reject cross-tenant artifact references.
- A failed QA report must name the defective stage and machine-readable correction target; do not simply regenerate everything.

## Required release sequence

```text
provider jobs complete
  → persist all canonical outputs
  → assemble/render master
  → ffprobe + full decode
  → visual/audio/script QA
  → targeted bounded correction OR human review
  → final approval record
  → Telegram/SaaS delivery
```

Delivery from the provider-completion webhook is permitted only for explicitly labelled previews. A preview must not be marked final, archived as approved, or bypass the master QA path.

## Acceptance tests

1. **Reachability:** the agent chooses the media tool and the call reaches the real worker with tenant/project IDs.
2. **Concat normalization:** two clips with different codecs, frame rates, timebases, and audio layouts produce one decodable master with the requested duration.
3. **Layers:** a fixture proves timed subtitles, a corner logo with safe margins, and dialogue-led music ducking.
4. **Artifact integrity:** every input/output hash and URL is persisted and tied to the workflow step.
5. **QA pass:** a compliant fixture reaches delivery only after technical and visual QA records exist.
6. **QA fail:** a seeded defect blocks final delivery and requeues only the relevant stage within a configured retry limit.
7. **Async recovery:** a delayed callback and a restart both resume the correct run and step.
8. **Idempotency:** duplicate callbacks and duplicate render requests create neither duplicate charges nor duplicate deliveries.
9. **Human override:** an explicit, auditable approval can release a known non-critical issue; silence or generic chat text cannot.
10. **Preview semantics:** preview delivery is visibly labelled and cannot be mistaken for the approved final master.

## Concrete single-VM sidecar hardening

For a temporary Oracle-VM sidecar, keep the contract declarative and closed: ordered HTTPS inputs, bounded output profile, whitelisted transitions, optional logo/SRT/music fields, exact callback URL, and a caller-generated idempotent job ID. Never accept raw FFmpeg/filter arguments, local paths, shell snippets, or caller-selected callbacks; invoke subprocesses with an argv list and `shell=False`.

Before downloading, reject URL credentials, fragments, non-HTTPS schemes, localhost/`.local`, non-443 ports, and hosts resolving to private, loopback, link-local, multicast, reserved, or unspecified addresses. Revalidate redirect targets. Bound request JSON, subtitle text, clips, per-asset bytes, total bytes, render duration, process time, and encoder concurrency.

A lightweight durable queue can use one atomically replaced `job.json` per job directory with `queued → running → completed|failed`. Duplicate IDs return existing state; service startup requeues interrupted `queued/running` jobs. Callback failure is tracked separately and must not erase a successfully rendered master.

Normalize every clip before concat: target scale/pad, FPS, SAR, timebase, pixel format, stereo 48-kHz audio, and bounded synthesized silence for clips without audio. Verify success with a complete `ffmpeg -xerror -f null -` decode plus FFprobe. For layer tests, compare frame/audio hashes against a baseline instead of trusting a `features_applied` flag.

In Scena, reuse provider-agnostic `video_jobs`: `model='oracle-ffmpeg'`, `task_type='video_composition'`, `cost_credits=0`, and the legacy `piapi_task_id` for the external sidecar job ID. Authenticate callbacks, validate the output URL against the configured sidecar base, correlate only through the D1 row, and ignore callback-supplied client/workflow metadata for authorization. The workflow resume call is `recordWorkflowAsyncResult(env, runId, stepKey, status, payload)`; background continuation uses `ctx.waitUntil`, never `env.waitUntil`.

Add the render tool to both the agent async-stop set and workflow runner async-tool set. After callback, technical probe is not creative QA: feed the complete master as `video_url` to multimodal QA, permit at most one no-credit rerender for deterministic edit/crop/logo/subtitle/audio defects, and route identity/product/anatomy/scene/motion defects to human review before paid regeneration. Use the real workflow context field `validationGate` rather than inventing `gate`, and inspect that type’s actual text field before composing the final approval prompt.
