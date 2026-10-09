---
name: autonomous-video-production-workers
description: Use when creating isolated Hermes video-production workers.
version: 0.1.0
author: W.Alter, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Hermes, profiles, video, production-queue, Google-Drive, QA, adapters]
    related_skills: []
---

# Autonomous Video Production Workers

Use this class-level workflow to create or maintain a specialized Hermes profile that turns a production queue of reference videos into verified, brand-adapted deliverables. The worker is not a general assistant: it owns queue intake, local media materialization, reference reconstruction, asset/video-provider boundaries, QA, Drive delivery, and durable job state.

Keep the profile's orchestration rules short in `SOUL.md`. Put the actual pipeline in the production skill, and keep provider-specific execution behind narrow adapters. The queue, Drive assets, reconstruction skill, target blueprint, and structured calibration files are the sources of truth; conversational memory is not a production database.

### Preserve semantic authority when decomposing the worker

A multi-stage profile is an execution architecture, not permission to summarize away the production logic. If the authoritative reconstruction skill contains the prompt compiler, reference-authority hierarchy, timestamp/state model, dialogue policy, asset-materialization contract, provider capability rules, QA/repair logic, and post-production constraints, those semantics must remain available through either:

- one complete canonical skill loaded at the relevant decision point; or
- stage skills plus structured artifacts whose contracts preserve every generation-critical field.

Do not replace a complete skill with a short orchestrator and terse stage summaries merely because the bundle has more files. Code, schemas, and smoke-test scripts do not compensate for missing semantic instructions. Treat a stage as incomplete when it emits generic prompts instead of a provider-ready timeline, omits internal cuts/source-content end/padding, lacks explicit reference mapping, or declares prompt-only target assets complete where reference-conditioned materialization is required.

Before production, perform a semantic coverage audit against the authoritative source. Use `references/lossless-semantic-decomposition.md` for the coverage matrix and artifact-level checks.

## When to Use

- Creating an isolated Hermes profile for autonomous video production.
- Wiring a Google Sheets/Drive production queue to a reference-video reconstruction pipeline.
- Auditing whether a video worker can ingest, materialize, generate, QA, deliver, and resume jobs safely.
- Adding or reviewing image/video provider adapters for a reconstruction worker.

Do not use this as a generic Hermes profile tutorial, a casual video-analysis workflow, or a substitute for the project's reference-reconstruction skill.

## Prerequisites

- A current Hermes installation and the profile-management CLI.
- The production skill's authoritative source. It may be a validated ZIP bundle, or—when the user explicitly says the attached Markdown is the actual skill—the Markdown can be installed directly as the profile-local `SKILL.md`. Do not invent a missing bundle. Audit every referenced `templates/`, `scripts/`, `schemas/`, `references/`, and `tests/` path before execution; implement deterministic runtime components under the profile rather than making execution depend on a nonexistent archive.
- Local `ffmpeg`, `ffprobe`, Python, and `yt-dlp`.
- Google OAuth credentials with read access to Sheets and Drive for validation; write scopes may be needed only for production delivery.
- Explicit image and video provider configuration. Never infer endpoints or credentials from a filename, a prompt, or a pending provider record.

## Architecture

```text
Hermes profile
├── SOUL.md                    # short role and invariants only
├── config.yaml                # isolated model, tools, runtime defaults
├── .env                       # profile-local secrets, mode 0600
├── auth.json                  # only required profile credentials
├── skills/
│   └── video-reference-reconstruction/
├── workspace/
│   ├── jobs/                  # durable per-row state and artifacts
│   ├── downloads/             # materialized source media
│   ├── cache/
│   └── batch_reports/
├── calibration/
│   ├── qa_policy.json
│   ├── creative_preferences.json
│   ├── accepted_examples/
│   └── rejected_examples/
└── logs/
```

A canonical queue row identity is `GSHEET_<spreadsheet-id>_ROW_<row-number>`. Persist it in every job artifact and never use a conversational turn ID as the only production identity.

## Procedure

### 1. Inspect before changing anything

1. Read the live Hermes version, active profile, profile list, global config path, and current tool conventions.
2. Inspect an existing working profile only to reuse proven model/provider conventions; do not clone its personal memory, unrelated skills, messaging integrations, or broad SOUL.
3. Record the target profile path before creating it.
4. After every profile-level change, verify the target profile explicitly. Never assume a command aimed at the new profile modified only that profile.

Completion criterion: the existing profiles remain unchanged, and the target path is known before writes begin.

### 2. Create a truly isolated profile

Use the profile manager with bundled-skill seeding disabled:

```bash
hermes profile create <profile-name> --no-skills \
  --description "Autonomous reference-video production worker."
```

Then create only the required directories listed above. Inspect what the Hermes version generated: some versions create a small profile metadata file before a full `config.yaml` exists. Normalize the profile-local `config.yaml` explicitly and verify with `hermes profile show <profile-name>` and `hermes -p <profile-name> config check`.

Set the profile-local memory policy to disabled unless a narrowly scoped production memory backend is deliberately required. Do not copy the user's personal profile, general preferences, broad session history, or general-purpose memory into the worker.

### 3. Minimize tools and integrations

Expose only the workflow's required capabilities:

- terminal/process execution;
- file/filesystem operations;
- Python/code execution;
- vision/image understanding;
- image generation/editing;
- skills.

Disable web, browser, messaging, email, Home Assistant, social search, TTS, delegation, cron, generic video generation, and unrelated MCP servers unless a specific production design requires them. A provider adapter is not a reason to expose arbitrary HTTP or a broad browser tool to the worker. If the worker's explicit pipeline includes a GENERATE stage, retain `video_gen` and disable only unrelated media routes (for example BFL or voice); verify the effective profile exposure instead of applying generic minimization against the stated production design.

Verify the effective profile tool list, not only the YAML. Tool inheritance and platform-specific lists can expose more than a minimal config suggests. Use the profile launcher when enabling/disabling toolsets and start a fresh session after changes.

### 4. Keep secrets and credentials local

- Put API keys in the profile `.env`, mode `0600`.
- Keep secrets out of `SOUL.md`, skills, queue snapshots, reports, prompts, and model-visible status text.
- Copy or authorize only the credentials required by this worker. A profile can have its own `auth.json`; do not silently rely on the default profile's private credential state.
- Use profile-local Google token/client-secret paths when the worker must run independently.
- Treat generated Drive URLs and provider job URLs as sensitive operational data; persist receipts locally, but do not print bearer-like signed URLs.

The worker may use a client-owned video key while keeping its LLM/reasoning provider separate. Model selection and video-provider selection must remain independent configuration concerns.

### 5. Install and audit the authoritative production skill

When a ZIP bundle is supplied, validate its archive structure and frontmatter before installing. When the user explicitly identifies an attached Markdown file as the actual skill, install that file directly as the profile-local `skills/<skill-name>/SKILL.md`; do not request or wait for a nonexistent ZIP.

After installation:

1. Verify the frontmatter name/version and hash the installed file.
2. Extract all referenced paths under `templates/`, `scripts/`, `schemas/`, `references/`, and `tests/`.
3. Classify each as procedural support, deterministic runtime, schema validation, provider contract, or regression fixture.
4. Keep orchestration logic in the skill; put deterministic behavior in profile-level `runtime/` and `scripts/`.
5. If a referenced component is absent, implement the narrow runtime component locally or report the missing procedural support explicitly. Never claim a placeholder, prompt-only image call, or untested provider endpoint is operational.

The attached-MD path is valid when the user states it is authoritative; the skill need not be discoverable through a ZIP installer to be usable by the profile.

### 6. Configure the queue as data, not as prompt prose

Store a non-secret queue configuration with:

- spreadsheet ID and title;
- requests tab and brand-assets tab;
- column mapping;
- pending definition;
- top-to-bottom ordering;
- supported command modes;
- completion transaction.

Before production, read live sheet metadata and the header rows. Do not assume the schema merely because configuration contains the expected labels. A pending row requires a non-empty reference video and `FINISHED` not true. A finished row with an empty result is inconsistent and must be reported, not silently repaired.

Supported command semantics should resolve deterministically:

```text
Do the next one     -> NEXT, count 1
Do the next N       -> NEXT_N, count N
Do all remaining    -> ALL_REMAINING
How many are left?  -> STATUS_ONLY, no production
```

### 7. Validate Google access read-only first

Use Drive for file metadata and Sheets for values when both APIs are available. If the Sheets values call returns a service-disabled error while Drive access works, use a live Drive XLSX export as a read-only fallback, parse the workbook's sheet names and cell values, and still validate the actual header rows and pending count. This is a compatibility fallback, not permission to write through Drive or to treat an exported snapshot as a permanent production source.

The validation script must report its read source, headers, pending row numbers, inconsistent rows, and `writes_performed: false`. It must never call update, append, clear, checkbox, or result-writing methods.

### 8. Materialize the actual reference video

Resolve the source type before analysis:

- Google Drive: use Drive file access and download bytes, not Drive-page scraping.
- Public/social URL: use the reconstruction skill's downloader adapter and `yt-dlp --no-playlist`.
- Direct media URL: download bytes, then validate; fall back to the public extractor only when appropriate.

Always write a local source manifest containing source kind, locator, local path, hash, and fetch status. Analyze the local video, never the webpage HTML or a remote preview. Do not implement DRM bypass or access-control circumvention.

### 9. Persist stage state and enforce the delivery transaction

Each job directory must contain stage receipts and resumable state. Reuse valid upstream artifacts after interruption; do not restart the entire job merely because a downstream stage failed.

The only successful completion order is:

```text
final QA passes
→ final video exists and decodes
→ upload final video to Drive
→ obtain stable Drive URL
→ write RESULT
→ re-read and verify RESULT
→ check FINISHED
→ re-read and verify FINISHED + RESULT
→ write delivery receipt
```

If any step fails, leave `FINISHED` unchecked and preserve the failed stage, error, inputs, and retry lineage. Generation completion is never equivalent to queue completion.

### 10. Keep media providers behind narrow adapters

The reconstruction skill owns Creative DNA, OVERRIDE, target blueprint, storyboard planning, prompts, QA, and repair strategy. The provider layer only renders and retrieves media.

Use narrow contracts such as:

```text
image_materialize(image_job.json)
video_generate(generation_spec)
video_status(job_id)
video_download(job_id)
```

The image boundary must require a real reference-conditioned edit mode, existing and decodable input images, input hashes, and a post-call materialization receipt with `binding_verified: true`. A prompt mentioning a filename is not an image binding.

The video boundary must have explicit provider/model/endpoint configuration and must return durable job/file identifiers. Do not allow the worker to hand-write arbitrary provider HTTP throughout the pipeline. If the adapter is absent, return a structured blocked state; never invent credentials, endpoints, job IDs, output paths, or successful receipts.

### 11. Run non-destructive dependency and script checks

Exercise real commands, not only `which` checks:

- encode and decode a tiny synthetic MP4 with `ffmpeg`;
- inspect it with `ffprobe` including streams and frame counts;
- run `yt-dlp --no-playlist --simulate` against a public test URL;
- compile or smoke-run Python scripts shipped by the production skill;
- validate profile config and skill discovery.

Do not start paid image/video generation during setup validation. Dependency warnings should be reported with their operational impact, not turned into permanent refusals.

### 12. Calibrate from evidence

Initialize `qa_policy.json` and `creative_preferences.json` as empty/default structures. Add client preferences only after they are validated in test batches. Keep accepted and rejected examples as explicit artifacts with provenance. Do not invent a client's aesthetic preferences from the first queue row or from generic branding assumptions.

## Reference Files

- `references/profile-isolation-and-tool-minimization.md` — tested profile creation, credential separation, and effective-tool verification.
- `references/read-only-google-queue-validation.md` — Sheets API → Drive XLSX fallback, header checks, pending-row logic, and no-write validation.
- `references/fail-closed-media-adapters.md` — image-binding receipts and narrow video-provider contracts.
- `references/video-worker-verification-matrix.md` — bundle integrity, effective tool exposure, no-spend smoke checks, and honest delivery boundaries.

## Pitfalls

- Cloning the default profile copies unrelated skills, memory, integrations, and personal behavior into a worker.
- A skill source may be a direct authoritative Markdown file; do not impose a ZIP-only installer contract when the user explicitly says no ZIP exists.
- Audit referenced external paths before execution. Missing prompt templates and missing deterministic scripts are different classes of gap; implement the latter locally and report the former.
- Drive metadata access does not prove the Sheets values API is enabled; validate both and use the tested export fallback when appropriate.
- A tool appearing in the global list does not mean it is safe for a specialized profile; verify effective profile exposure.
- A downloaded preview, webpage, or signed provider URL is not necessarily the actual local media artifact.
- A generated PNG/MP4 without a binding or delivery receipt is not a completed stage.
- Never update `RESULT` before obtaining and validating the stable Drive URL, and never set `FINISHED` before re-reading both cells.
- Do not put durable production state in conversation history or opaque memory.

## Verification Checklist

- [ ] Existing profiles were inspected and not modified.
- [ ] Target profile has isolated `config.yaml`, `.env`, `SOUL.md`, `skills/`, `workspace/`, `calibration/`, and `logs/`.
- [ ] Effective tool list contains only required workflow capabilities.
- [ ] Personal memory and unrelated messaging/integrations are not copied.
- [ ] Authoritative production skill source is installed directly or from a validated archive and is discoverable by the target profile.
- [ ] External skill references were audited and classified.
- [ ] Queue schema was read live and headers match.
- [ ] Queue validation reports pending rows and performed no writes.
- [ ] Reference media is materialized locally before analysis.
- [ ] Every job has a stable row identity and resumable stage state.
- [ ] Image jobs bind actual source bytes and produce verified receipts.
- [ ] Video provider calls go through a narrow configured adapter.
- [ ] `ffmpeg`, `ffprobe`, `yt-dlp`, and production Python scripts execute successfully.
- [ ] Paid generation was not triggered by validation.
- [ ] Final delivery follows QA → Drive → RESULT → verification → FINISHED → verification.
