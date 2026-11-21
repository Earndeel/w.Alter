# Anthropic-compatible gateway validation: tools, streaming, and Hermes

Use this when a third-party Anthropic Messages endpoint works in one client but fails or retries in Hermes.

## Capability probe

Test the exact requested model directly with a minimal request containing one harmless function. Run both non-streaming and streaming variants. A valid streaming tool response should contain Anthropic-style `message_start`, `content_block_start` with `type: tool_use`, JSON deltas, and a terminal message event.

A successful direct probe establishes model/provider capability only. It does not establish Hermes adapter compatibility.

## Transport and envelope checks

- Require the expected HTTP content type.
- For JSON responses, reject application error envelopes even when HTTP status is 200.
- For SSE, validate event ordering and required fields rather than treating any HTTP 200 stream as usable.
- Record the exact model returned by the provider and reject silent model substitution.

## Kie-bound proxy normalization

At the final upstream boundary only:

1. Preserve an existing Authorization header.
2. If Authorization is absent and the client supplied an Anthropic API-key header, convert that credential to Bearer form and remove the original header.
3. Use a browser-compatible User-Agent when the gateway's WAF distinguishes client signatures.
4. Apply the same normalization to auxiliary calls such as token counting.
5. Leave non-Kie upstream headers unchanged; cover both branches with unit tests.

Never print, dump, or persist the credential while diagnosing headers.

## Hermes differential diagnosis

When the direct probe succeeds but Hermes retries:

1. Restrict Hermes to the exact provider, model, and smallest relevant toolset.
2. Disable implicit fallbacks or verify the effective provider/model from request evidence.
3. Capture the first underlying adapter exception in verbose logs; the final “failed after retries” line is only a summary.
4. Compare direct and Hermes payload fields: streaming flag, system format, tool schema, metadata, beta headers, and usage-event schema.
5. Inspect proxy events and raw executor output separately.
6. Do not retry the same large execution prompt until the minimal probe passes.

## Planner/executor proof pattern

A planner response is not an end-to-end success. Require all of the following:

- Planner output validates against a strict versioned JSON contract.
- Executor emits a strict execution report.
- A harmless real artifact is created and read back.
- The stated verification command actually passes.
- Any replan is triggered only by a structured blocked/failed report and is capped.

## Measured session note (2026-07-10)

A Fable planning call through pxpipe converted 30,472 explicitly selected context characters into two images; Kie reported 1,442 input tokens, and the JSON plan validated. A direct `claude-sonnet-5` streaming probe emitted a real tool-use block. The Hermes executor path still failed before producing its harmless artifact, so that integration remained fail-closed and was not production-ready at session end.
