---
name: fal-openapi-schema-discovery
category: mcp
description: Discover exact parameter schemas for any Fal.ai model via their OpenAPI endpoint. Bypasses MCP limitations and documentation gaps by fetching the raw OpenAPI 3.0.4 spec directly.
tags: [fal.ai, openapi, schema, model-parameters, video-generation, image-generation]
trigger: Need exact parameters/types/options for a Fal.ai model endpoint; MCP doesn't expose full schema; documentation is missing or outdated.
---

# Fal.ai OpenAPI Schema Discovery

Fal.ai exposes an undocumented OpenAPI JSON endpoint that returns the exact input schema for any model, including parameter types, defaults, enum options, required fields, and descriptions.

## Discovery Endpoint

```
GET https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<model_id>
```

The `model_id` uses the **queue** format (not the REST format). Examples:
- `bytedance/seedance-2.0/reference-to-video` (no `fal-ai/` prefix)
- `fal-ai/kling-video/v3/pro/text-to-video` (some have the prefix)

## Response Structure

The response is OpenAPI 3.0.4. The schema lives in:

```json
{
  "components": {
    "schemas": {
      "<ModelName>Input": {
        "properties": {
          "param_name": {
            "type": "string|boolean|array|number",
            "default": "...",
            "enum": ["opt1", "opt2"],
            "description": "What this param does"
          }
        },
        "required": ["param1", "param2"]
      }
    }
  }
}
```

## Usage Pattern

```python
import urllib.request, json

def get_model_schema(endpoint_id):
    url = f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={endpoint_id}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    
    schemas = data.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        if "Input" in name:
            return {
                "schema_name": name,
                "required": schema.get("required", []),
                "properties": schema.get("properties", {})
            }
    return None

# Example
schema = get_model_schema("bytedance/seedance-2.0/reference-to-video")
# Returns: prompt (required), image_urls, video_urls, audio_urls, duration, etc.
```

## How to Find Endpoint IDs

Use `mcporter call fal.list_models search=<keyword>` to find model IDs, then test with the OpenAPI endpoint.

Some models have different ID formats:
- `fal-ai/...` — standard prefix
- `bytedance/...` — direct provider prefix (Seedance 2.0)
- `xai/...` — provider prefix (Grok)

Always test the OpenAPI endpoint to verify the exact ID works.

## Store in Database

For AI agents that generate payloads, store the schema in a DB table:

```sql
CREATE TABLE fal_endpoints (
    id TEXT PRIMARY KEY,
    endpoint TEXT NOT NULL,
    schema_json TEXT DEFAULT '{}',  -- JSON of properties
    use_case TEXT DEFAULT '',
    cost_per_unit REAL DEFAULT 0,
    active INTEGER DEFAULT 1
);
```

The LLM receives all endpoint schemas as context to generate conformant payloads.

## Pitfalls

1. **No `fal-ai/` prefix for some models** — Seedance 2.0 uses `bytedance/seedance-2.0/...` without the `fal-ai/` prefix when querying OpenAPI, but `fal_client.submit()` needs the full endpoint.
2. **Early access models** — Some endpoints return schemas but reject actual calls (403). The OpenAPI endpoint still works.
3. **`type: unknown`** — Some fields show `unknown` type (usually seed, end_user_id). Treat as optional.
4. **`enum` is the list of valid options** — Use these for dropdowns in UIs and as constraints for LLM payload generation.
