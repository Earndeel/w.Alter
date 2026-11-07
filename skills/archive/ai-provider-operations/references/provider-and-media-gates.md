# Provider and media gates

## Route gate

Resolve exact model ID, endpoint, API mode, region, account, credential scope, entitlement, quota, and budget. Use a minimal authenticated probe through the intended client and inspect route metadata before evaluating quality.

## Model and parameter exposure gate

1. Check the official model page for the exact ID, supported API routes, and documented quality/settings.
2. Check the active profile's selected provider and enabled toolsets, then inspect the current session's runtime schema. Treat configured and authenticated as separate from callable in-session.
3. Inspect the provider catalog, model-resolution logic, and request builder. Classify controls as **call-time arguments**, **configuration-only choices**, or **fixed payload fields**; confirm the exact model ID actually sent.
4. Compare access routes independently. For image generation, first-party Codex CLI `$imagegen`, Hermes Codex OAuth, and direct OpenAI API are separate integrations; support on one route does not imply support on another.
5. Report official availability separately from what this session can invoke, including any alternative route's authentication and billing requirements. Do not change configuration or submit a billable generation for a catalog question.

## Evaluation gate

Normalize prompt, files, system instructions, tools, permissions, timeout, iteration cap, and rubric. Record latency, tokens, cost, errors, successful-task rate, and artifact quality separately; mark provider-aborted runs and unverified values explicitly.

## Media gate

Bind real source bytes or provider handles and record hashes, dimensions, prompt, job ID, output ID, and stage state. Download the artifact, run metadata and full decode, review visual/audio/brief compliance, and keep provider failure separate from local tracking failure.

## Release gate

Keep clean masters and versioned derivatives. Run master-level ASR when copy matters, validate captions and loudness, verify browser codec fallback and recipient-visible playback, and treat upload or a stable URL as transport evidence rather than delivery proof.
