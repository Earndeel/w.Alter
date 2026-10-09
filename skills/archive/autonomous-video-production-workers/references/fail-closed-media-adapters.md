# Fail-closed media adapters

## Image materialization

A source-conditioned image task is valid only when the provider receives the actual source image bytes or an explicit image input handle. A filename mentioned in prompt text is not binding evidence.

Before the call:

1. Check every `input_images[]` path exists and decodes.
2. Record width/height and SHA-256.
3. Set `mode: reference_conditioned_edit` and `required_binding: true`.
4. Confirm the adapter supports the requested image input mode.

After the call, write a receipt containing the job ID, provider/model, mode, bound input hashes, prompt hash, output hash, output path, and `binding_verified: true`. If the adapter cannot bind the source, return `BLOCKED_IMAGE_INPUT_BINDING`; do not generate a prompt-only substitute.

## Video provider boundary

Keep provider execution behind these narrow operations:

```text
video_generate(generation_spec)
video_status(job_id)
video_download(job_id)
```

The reconstruction skill owns Creative DNA, OVERRIDE, target blueprint, prompt compilation, and QA. The adapter owns only provider submission, status reconciliation, and media download. It must require explicit endpoint/model/credential configuration and return durable job/file IDs.

If configuration is absent, return a structured `BLOCKED_VIDEO_PROVIDER` state. Never invent a URL, key, job ID, signed download URL, or output file. A generation submission is not a completed artifact: status must reach a terminal success state, the file must download and decode, and the worker must persist the result before QA.

## Reuse and retry

Retain job IDs and stage receipts across interruptions. Poll the existing job before submitting a duplicate. Retry only the failed boundary and preserve prior candidates; never overwrite the only artifact.
