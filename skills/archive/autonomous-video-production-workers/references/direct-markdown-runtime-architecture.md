# Direct-Markdown skill installation and profile-runtime architecture

Use this reference when the user supplies a Markdown file as the authoritative production skill and explicitly says no ZIP/package exists.

## Installation rule

Install the file directly as the target profile's local skill:

```text
<profile>/skills/<skill-name>/SKILL.md
```

Validate the frontmatter name/version and hash the installed file. Do not wait for a ZIP, create a fabricated archive, or recreate missing procedural content from memory. A direct Markdown skill is valid when the user identifies it as the actual skill.

Example installer contract:

```python
source = /root/.hermes/attachments/VIDEO_RECONSTRUCTION_SKILL_v0.8.md
target = <profile>/skills/video-reference-reconstruction/SKILL.md
assert "name: video-reference-reconstruction" in source
assert "version: 0.8.0" in source
copy2(source, target)
```

## External-reference audit

Before execution, extract and classify every referenced path under:

- `templates/`: procedural prompt/analysis/QA aids; these are not deterministic runtime code.
- `scripts/`: deterministic helpers that must either be present or be implemented under the profile.
- `schemas/`: machine validation contracts.
- `references/`: provider/runtime contracts and explanatory detail.
- `tests/`: regression fixtures and acceptance tests.

Persist the audit as a workspace artifact. Do not silently treat an absent template or fixture as present.

## Profile-local runtime split

Keep the Markdown as the complete orchestration/procedural authority. Put deterministic execution under the profile, for example:

```text
<profile>/runtime/
  queue_adapter.py
  drive_adapter.py
  google_auth.py
  reference_fetcher.py
  media_analysis.py
  reference_board.py
  panels.py
  image_materializer.py
  provider_contract.py
  provider_adapter.py
  generation_planner.py
  completion_transaction.py
<profile>/scripts/
  google_queue.py
  drive_media.py
  fetch_reference_video.py
  analyze_video.py
  compose_reference_board.py
  extract_storyboard_panels.py
  image_materialize.py
  video_provider_adapter.py
  completion_transaction.py
```

The narrow public boundaries are:

```text
image_materialize(image_job.json)
video_generate(generation_spec)
video_status(job_id)
video_download(job_id)
```

## Queue/Drive behavior

Read live Google Sheet metadata and headers first. A read-only fallback is valid when Sheets Values API is disabled but Drive export works: export the Google Sheet as XLSX through authenticated Drive, parse the named tabs and headers, and report `read_source=drive_xlsx_export_fallback`. Never write through the fallback during validation.

Pending rows require non-empty `REFERENCE VIDEO` and `FINISHED` false. Preserve top-to-bottom row order and use stable IDs:

```text
GSHEET_<spreadsheet-id>_ROW_<row-number>
```

## Media/provider gates

- Public/social references use `yt-dlp --no-playlist`; Google Drive references use Drive file bytes, never page scraping.
- Image materialization must preflight actual input image paths, decode them, hash them, bind the bytes through a reference-conditioned edit adapter, and write a receipt with `binding_verified=true`. A filename in a prompt is not a binding.
- Video provider calls must be behind a configured adapter. Submission is not completion; persist task IDs, poll, download, probe, and preserve retry state.
- Completion is fail-closed: final QA → local final exists → Drive upload → stable URL → write RESULT → verify RESULT → check FINISHED → verify FINISHED+RESULT.

## Validation evidence

Run actual smoke tests, not only `which`: tiny FFmpeg encode/decode, ffprobe stream/frame inspection, `yt-dlp --no-playlist --simulate`, Python compilation/tests, profile config check, skill listing, and read-only queue validation. Do not run paid generation during setup validation.

## Hermes CLI nuance

On Hermes versions where `skills list` shows a local skill but `skills inspect <name>` fails to resolve it, treat the profile-local file and `skills list` output as the discovery evidence and record the CLI limitation; do not delete or reinstall a valid local skill merely because the inspect subcommand uses a different source resolver.
