---
name: kie-hermes-readonly-audit
description: Read-only audit of Kie.ai GPT-5.6-Luna through the Hermes Codex Responses transport.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [kie.ai, hermes, codex-responses, gpt-5.6-luna, reasoning, audit]
---

# Kie.ai / Hermes read-only audit

Use for a bounded compatibility check. The target is exactly `gpt-5-6-luna`; do not replace it with another model.

## Direct endpoint observation

Endpoint:

```text
https://api.kie.ai/codex/v1/responses
```

Use a short deterministic request with `model: gpt-5-6-luna`, bearer authentication, JSON content type, and a browser-like `User-Agent`. Inspect only sanitized response fields: HTTP status, response ID, response model, completion status, reasoning object, reasoning-token count, credits, and safe error text. Never display credentials or complete authorization values.

The accepted reasoning shape observed for this endpoint is:

```json
{"reasoning": {"effort": "max"}}
```

A flat `reasoning_effort` field is not equivalent: it has produced a body-level server error despite HTTP 200. A successful HTTP status is therefore insufficient; inspect the response body and completion status.

## Hermes transport observation

Use an isolated test context and inspect the outgoing request rather than trusting configuration. Confirm all of the following:

- URL is `https://api.kie.ai/codex/v1/responses`;
- model is exactly `gpt-5-6-luna`;
- `reasoning.effort` is `max`, not a default such as `medium`;
- the request includes a browser-like `User-Agent`;
- exactly one deterministic tool is present for the minimal tool test;
- the response is normalized as a Codex Responses result, including status, output, usage, and tool calls;
- temporary state shows whether a fallback was used.

A 403 from Kie or Cloudflare is an integration failure, even if direct calls succeed. Missing `User-Agent`, lost reasoning mapping, and an unexpectedly large tool registry are separate transport issues and must be reported separately.

## Verdict rules

- `OK`: direct and Hermes tests complete with the target model, intended reasoning, one tool, and no fallback.
- `OK_ADAPTER`: direct Kie works and only a localized Hermes adapter normalization remains.
- `KO`: Hermes is blocked, silently changes the reasoning level, sends the wrong tool set, or falls back.

Keep the final audit concise and point to the sanitized test artifacts. Do not claim viability from direct API success alone.