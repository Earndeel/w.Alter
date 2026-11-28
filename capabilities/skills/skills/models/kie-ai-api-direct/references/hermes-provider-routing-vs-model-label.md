# Hermes provider routing vs. model label

Use this when a model appears selected in Hermes Desktop but the expected provider dashboard shows no request.

## Core diagnostic

A displayed model name is not proof of provider routing. Verify the live worker/session carries **both**:

- the provider identity (for example `kie-gpt`), and
- the provider-native model ID (for example `gpt-5-6-luna`).

A worker running a friendly or alias model such as `gpt-5.6-sol` while runtime metadata reports another provider means the selector changed the model label/alias without changing the transport. In that state, zero Kie.ai logs is expected: no request crossed the Kie.ai boundary.

## Evidence order

1. Inspect the live session runtime metadata (`provider`, `model`, `base_url`, and billing fields when available).
2. Inspect the worker launch/runtime state; do not infer the provider from the UI label alone.
3. Confirm the selected value is equivalent to `MODEL --provider PROVIDER` and that the persisted session override contains both fields.
4. Only then inspect Kie.ai authentication, request headers, or dashboard logging.
5. For final verification, make one bounded request and confirm both local outbound evidence and Kie.ai-side logging/billing metadata.

## Stale-runtime trap

Provider plugins and Python routing code are loaded into the long-lived dashboard/gateway process. Editing source files or rebuilding only the frontend does not update an already-running backend. Compare the service start time with the integration change time.

Do **not** blindly restart the dashboard service: systemd may place spawned agents, proxies, language servers, and unrelated long-lived workers in the same cgroup, so a restart can terminate all of them. Before restart:

1. Inspect the service cgroup/process tree.
2. Identify active bounded jobs and unrelated long-lived children.
3. Prefer a controlled maintenance window or a backend design that isolates workers from the web service cgroup.
4. If interruption is material, report the stale-runtime finding and request approval rather than killing the process tree.

## Desktop/gateway verification pattern

Use the gateway protocol rather than a standalone CLI when the deliverable is Desktop routing:

1. Query `/api/model/options` and verify the target model is listed under the provider slug that owns its transport. For Kie GPT/Codex, that slug is `kie-gpt`; `kie` is the separate Claude/Gemini custom endpoint.
2. Open `/api/ws`, create an isolated session with both `model` and `provider`, then submit one bounded prompt.
3. Treat an empty `message.complete` event body as inconclusive: gateway deltas and persistence can carry the result separately. Read the stored session row and assistant message.
4. Verify `billing_provider`, `billing_base_url`, `billing_model`, response status, and provider-side billing before declaring success.

A known-good Kie GPT-5.6 check has this shape: `provider=kie-gpt`, `model=gpt-5-6-sol`, outbound `/gpt-codex/responses`, HTTP 200, and Kie billing metadata. Sending the same model with `provider=kie` routes to the Claude base URL and can produce a misleading 403; that is a routing error, not evidence that the GPT credential or model is invalid.

## Interpretation

- Wrong provider/base URL: routing defect; Kie.ai auth debugging is premature.
- Correct provider, no outbound request: client serialization or preflight failure.
- Correct outbound Kie.ai URL with HTTP response: inspect auth, UA, payload, and endpoint contract.
- Local HTTP failure with no Kie dashboard entry: do not assume the dashboard records edge-layer 4xx responses; retain local wire evidence.

## Walter Router one-shot runs can misreport an internal Hermes fallback (2026-10-23)

A successful walter_run result with routed.provider/routed.model and attempts[].ok=true is not proof that the requested route produced the answer. serve/run.py invokes Hermes and returns the requested route when the subprocess succeeds; Hermes can activate its own fallback chain inside that same subprocess. Inspect the exact child session in raw logs and read-only state.db billing_provider, billing_base_url and model before attributing an execution. Keep requested and observed route separate. Provider-side billing remains a separate check.

Observed evidence: session 20261022_195148_1d86c8 (source walter-router), 2026-10-22 19:51–19:55 UTC. walter_run reported claude-opus-5-5 via kie, one successful attempt, 215 seconds. agent.log showed repeated EmptyStreamError with HTTP 200 and zero bytes on https://api.kie.ai/claude, then at 19:54:25 UTC 'Fallback activated: claude-opus-5-5 → gpt-6-1-sol (kie-codex)'. Two successful model calls were logged at 19:54:52 and 19:55:14 UTC. state.db recorded model gpt-6-1-sol, billing_provider kie-codex, billing_base_url https://api.kie.ai/codex/v1/, cost_status unknown and cost_source none. This proves local transport and fallback attribution, not dashboard visibility or an amount charged. The terminal assertion run was independently confirmed in walter_logs.
