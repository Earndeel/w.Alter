# Desktop provider-route evidence template

Use this compact record for any fresh Desktop routing smoke test. Redact secrets; keep exact model and route values.

```text
Date/time UTC:
Desktop session ID:
Backend process start/reload time:

Selected presentation provider:
Selected model ID:
Resolved runtime provider:
Resolved API mode:
Resolved base URL:

Outbound method + URL:
Auth presence: yes/no (never record token)
User-Agent class:
Request body family: chat / Anthropic Messages / Responses
SSE event count or terminal event:
HTTP status:
Provider response model:

billing_provider:
billing_base_url:
billing_model:
api_call_count:
Fallback activated: yes/no

Evidence class:
Unknowns:
```

Acceptance requires the outbound URL and response metadata to match the model-family route. A picker row or resolver unit test alone is insufficient.
