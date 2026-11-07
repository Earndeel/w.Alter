# Kie.ai Callback and Progress Notes

## Verified API contract

Kie.ai Market generation tasks are created with:

```text
POST https://api.kie.ai/api/v1/jobs/createTask
```

The request may include `callBackUrl`:

```json
{
  "model": "bytedance/seedance-2",
  "callBackUrl": "https://example.com/webhook/kie",
  "input": {
    "prompt": "A product showcase video",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 5
  }
}
```

The create response returns a task ID; HTTP 200 means the task was accepted, not that media is ready.

The current Seedance 2.0 documentation says to use `callBackUrl` for automatic notifications **upon completion**, instead of polling the status API. Do not describe this as a guaranteed realtime progress stream.

## Progress and canonical status

For Market models, query:

```text
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
```

The documented states are:

- `waiting` — task is queued/waiting;
- `queuing` — task is in the processing queue;
- `generating` — task is being processed;
- `success` — completed;
- `fail` — failed.

The task-detail response contains fields such as `taskId`, `model`, `state`, `resultJson`, `failCode`, `failMsg`, timestamps, `progress`, and `creditsConsumed`. The documentation includes `progress` in the example response, but does not promise that every progress change produces a webhook event.

Older model integrations may expose the legacy endpoint:

```text
GET https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=<taskId>
```

Prefer `recordInfo` for Market models; keep the legacy endpoint as a model-specific fallback only when the provider documentation or observed response requires it.

## Recommended hybrid design

1. Submit with `callBackUrl` and persist the local job plus provider `taskId`.
2. While the UI needs a percentage, poll `recordInfo` around every 2–3 seconds with bounded backoff and a timeout.
3. On callback, verify the signature and deduplicate by task ID/event ID.
4. Fetch `recordInfo` once more after accepting the callback when the callback body is incomplete or its schema is not explicitly documented.
5. Mark the local job terminal with an idempotent upsert, stop further polling, and immediately copy the result media to durable storage because provider URLs may expire.

## Callback verification

Kie.ai's Common API documentation describes optional webhook HMAC verification configured through a `webhookHmacKey` in the Kie.ai settings page. When enabled, callbacks include:

- `X-Webhook-Timestamp` — Unix timestamp in seconds;
- `X-Webhook-Signature` — Base64-encoded HMAC-SHA256 signature.

The documented signature formula is:

```text
base64(HMAC-SHA256(taskId + "." + timestamp, webhookHmacKey))
```

Use constant-time comparison and reject stale/replayed timestamps. Keep the HMAC key in the provider secret store, never in source control or a callback URL.

The documentation uses both `taskId` and `task_id` in different verification instructions. Treat the actual provider callback body as authoritative for the identifier field, but normalize it internally to `taskId` and test the signature against a captured callback before shipping.

## Implementation notes for Cloudflare/Scena

A suitable flow is:

```text
createTask -> D1 job(task_id, status, progress)
                    |
                    +-> polling loop for UI progress
                    |
                    +-> POST /webhook/kie
                          -> HMAC verify
                          -> idempotent task update
                          -> recordInfo reconciliation
                          -> R2/media persistence
```

The callback handler should acknowledge only after the event has been durably accepted. Do not perform a long media download before responding; enqueue or schedule that work where the runtime supports it.

## Authoritative references

- Seedance 2.0: https://docs.kie.ai/market/bytedance/seedance-2
- Unified task status: https://docs.kie.ai/market/common/get-task-detail
- Webhook HMAC verification: https://docs.kie.ai/common-api/webhook-verification
