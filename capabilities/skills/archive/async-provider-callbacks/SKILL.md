---
name: async-provider-callbacks
description: "Use for provider callbacks and progress polling."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [async, callbacks, webhooks, polling, providers, jobs, video]
    related_skills: [webhook-subscriptions, kie-video-generation]
---

# Async Provider Callbacks

A class-level workflow for third-party APIs that create asynchronous jobs and expose some combination of a callback URL, a task-status endpoint, and downloadable results. The central distinction is operationally important: a callback may be a terminal completion notification rather than a stream of progress events.

## When to use

Use this skill when an external provider:

- returns a task/job ID instead of the result in the creation response;
- accepts a callback/webhook URL; or
- requires polling for status, progress, or result URLs.

This covers video/image generation APIs, media processing, long-running exports, and similar provider jobs. It is complementary to the Hermes `webhook-subscriptions` skill: this skill handles the **outbound provider job lifecycle and inbound callback handler**, while that skill handles Hermes' generic inbound webhook subscription platform.

## Workflow

1. **Read the provider's current documentation first.** Confirm the create endpoint, callback field spelling/casing, callback semantics, status endpoint, terminal states, result shape, retry behavior, result URL retention, and signature scheme. Do not infer that a callback is a progress stream merely because the API has a `progress` field.
2. **Create a public HTTPS callback route.** Give each provider a dedicated route or a provider-scoped secret. The handler must return quickly; enqueue or persist work instead of doing a long download or expensive transformation inline.
3. **Submit the job with the callback URL.** Persist the provider name, model/variant, local correlation ID, provider task ID, creation timestamp, and initial state. If the provider only returns the task ID after creation, make the state transition explicit and recoverable rather than losing an untracked task.
4. **Choose the progress strategy.** If the provider documents completion-only callbacks, poll its status endpoint while the task is active when the product needs live progress. Start around 2–3 seconds, use bounded exponential backoff, and impose a job timeout (the provider's documented 10–15 minute guidance is a useful default for media jobs, not a universal constant). Stop polling on a terminal callback or terminal poll result.
5. **Treat the callback as a signal, not necessarily the canonical record.** Verify its signature, deduplicate by provider task ID/event ID, and fetch the provider's status endpoint if the callback body is incomplete or its schema is not explicitly documented. This also normalizes result URLs, failure details, credits, and progress fields.
6. **Make state transitions monotonic and idempotent.** A retry or late callback must not move `success` back to `generating`. Accept duplicate terminal notifications safely, record the raw provider event only after redacting secrets, and use an atomic compare-and-set/upsert where possible.
7. **Download or copy results immediately.** Presigned media URLs often expire. Store durable media in the application's own storage and retain provider metadata separately. Do not expose provider API credentials in callback URLs, logs, or client-side state.
8. **Verify with a real task.** A unit test of HMAC math is not enough: run one small provider job against a temporary callback endpoint, record the callback headers/body, compare it with a status query, test a duplicate delivery, and confirm the result download before declaring the integration complete.

## Security baseline

- Verify provider signatures before trusting task state or result URLs.
- Use constant-time signature comparison and reject stale timestamps when the provider supplies one.
- Keep callback secrets in the configured secret store; never put them in the repository or a public URL.
- Add request-size limits, structured logging with secret/result-token redaction, and idempotency protection.
- Return a fast 2xx only after the event has been durably accepted. Return a retryable 5xx when the event cannot be persisted.

## Provider-specific reference

`references/kie-ai-callbacks.md` contains the verified Kie.ai Market/Seedance pattern: `callBackUrl` completion semantics, `recordInfo` progress polling, task states, HMAC headers/formula, and the recommended hybrid architecture.

## Pitfalls

- **Completion webhook mistaken for realtime progress:** keep polling if the UI needs a percentage. Kie.ai's Seedance documentation explicitly describes `callBackUrl` as a completion notification.
- **Callback body treated as canonical without documentation:** fetch the provider record after receiving the event when the callback schema is underspecified.
- **Polling forever after a callback:** mark the task terminal atomically and cancel/skip further polls.
- **Assuming one status endpoint for every model family:** provider marketplaces often retain legacy endpoints alongside a newer unified endpoint.
- **Downloading later:** generated URLs may be short-lived even if the task record remains available.
- **No duplicate handling:** providers and intermediaries can retry delivery; task processing must be safe to repeat.

## Verification checklist

- [ ] Callback URL is reachable over HTTPS from the provider.
- [ ] Task ID is persisted and correlated with the local job.
- [ ] Signature, timestamp, and replay checks are tested.
- [ ] Completion and failure callbacks both update state.
- [ ] Progress polling has backoff, timeout, and cancellation.
- [ ] Duplicate and out-of-order events are harmless.
- [ ] Final status is reconciled with the provider's status endpoint.
- [ ] Result media is copied before provider URLs expire.
- [ ] A real end-to-end callback was observed, not merely mocked.
