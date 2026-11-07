# Provider webhook hardening pattern

Use this reference when a Scena provider callback can complete or fail a media job, trigger a refund, deliver to Telegram, advance a workflow, or call a customer webhook.

## Threat model

An inbound callback body is attacker-controlled unless a provider signature has been cryptographically verified. A correlation ID (`taskId`, `request_id`) is not authentication. Even a genuine callback can be replayed or race a poller/recovery job.

## Safe processing order

1. Parse the provider task ID; reject an empty ID.
2. Look up the job **only by the exact provider task ID**, scoped to the expected provider/tenant where available.
3. If no job matches, acknowledge with `missing_job: true`; never fall back to “latest pending job”.
4. If the local job is already `completed` or `failed`, acknowledge with `duplicate: true` before any external call or side effect.
5. Establish provider truth:
   - verify the provider’s HMAC/signature when supported; or
   - call the provider’s authenticated status/record endpoint with the task ID and use that response, not the callback body, for status and output URLs.
6. Transition the job conditionally, for example:
   ```sql
   UPDATE media_jobs
   SET status = 'completed', output_url = ?
   WHERE id = ? AND status NOT IN ('completed', 'failed')
   ```
7. Inspect D1 `meta.changes`. If zero, return `duplicate: true`.
8. Only after winning the terminal transition may the handler refund credits, deliver media, advance workflows, append ledger entries, or invoke customer callbacks.

## Why both checks matter

The early status check is cheap and avoids unnecessary provider calls. The conditional `UPDATE` is the actual race guard: two concurrent callbacks can both read a non-terminal state, but only one may win the transition.

## Credit safety

Refunds and ledger writes are side effects of the guarded transition, never unconditional consequences of a callback body. Apply the same class-level check to callback handlers, pollers, cron recovery, timeout cleanup, and manual retry paths.

## Behavioral tests

Add tests that execute the real handler path:

- **Forged body:** callback claims `completed` and supplies an attacker URL; mocked authenticated provider status returns the canonical URL. Assert only the canonical URL is persisted/delivered.
- **Replay:** submit a second callback for a terminal job, possibly with the opposite terminal state. Assert `duplicate: true`, no second delivery, no second refund, no second workflow transition, and no second outbound callback.
- **Unknown ID:** submit a valid-looking callback for an unrecognized task ID while another job is pending. Assert the pending job remains untouched.
- **Race contract:** make the conditional update return `meta.changes = 0`; assert all downstream side effects are skipped.
- **Provider verification failure:** provider status endpoint returns non-2xx or malformed data; assert 502/controlled failure and no local mutation.

## Migration-specific gate

When changing the default provider, review every inbound webhook and recovery poller as part of the migration. Provider routing is incomplete until callback truth, terminal idempotence, output extraction, and credit side effects are proven for the new provider.
