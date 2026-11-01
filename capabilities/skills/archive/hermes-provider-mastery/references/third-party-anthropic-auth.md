# Third-Party Anthropic Endpoint Auth

## Problem

Anthropic SDK auto-reads auth token from environment. When set to a placeholder,
it sends invalid Bearer header alongside correct x-api-key header. Some endpoints
reject the whole request.

## Symptoms

- curl with x-api-key header works fine
- Hermes/SDK returns HTTP 401 "Invalid API key"
- Debug shows SDK sends both Authorization Bearer and x-api-key headers

## Root Cause

SDK init reads auth token from env automatically. If env contains placeholder
or stale value, Bearer header is invalid. Endpoint checks Bearer first and
rejects before seeing valid x-api-key.

## Fixes

1. Set auth token env var to real API key in .env file
2. Or unset auth token env var entirely (endpoint must support x-api-key only)
3. Or patch adapter to clear auth_token for third-party endpoints

## Auth Flow

Provider config key_env resolves the API key. Anthropic adapter passes it
as api_key parameter. SDK also reads auth token from env. Both headers
are sent. Endpoint may reject if Bearer is invalid.

## Verification

Test with raw HTTP client (bypasses SDK) to isolate whether issue is
SDK-specific or endpoint-specific. If raw client works but SDK fails,
the problem is Bearer header injection.

## Claude Code Tool Name Emission

Third-party Anthropic proxies (aiprimetech, etc.) can cause Claude to emit its
**own native tool names** (`Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`)
instead of the Hermes names (`terminal`, `read_file`, `write_file`, `patch`,
`search_files`) sent in the tool schema. This happens because the proxy may
route through infrastructure that injects Claude Code system prompts or
tool definitions alongside the caller's schema.

### Impact

The model generates a tool call with `name: "Bash"`. Hermes validates against
`valid_tool_names`, doesn't find it, returns an error. After 3 retries the
turn is aborted as partial — user sees "Error: Model generated invalid tool
call: Bash" and the response is cut short.

### Fix (upstream)

`repair_tool_call()` in `agent/agent_runtime_helpers.py` includes an explicit
Claude Code → Hermes name mapping applied **before** fuzzy match:

```
Bash → terminal
Read → read_file
Write → write_file
Edit → patch
Glob → search_files
Grep → search_files
ls/find → search_files
cat/head/tail → read_file
sed → patch
```

This fix is in the Hermes source tree. If a future `hermes update` overwrites
it, re-apply the mapping in `repair_tool_call()` after the fast-path
normalization and before the fuzzy-match fallback.

### Verification

```bash
cd ~/.hermes/hermes-agent && python3 -c "
from agent.agent_runtime_helpers import repair_tool_call
class A: valid_tool_names = {'terminal','read_file','write_file','patch','search_files'}
a = A()
for t in ['Bash','Read','Write','Edit','Glob']:
    print(f'{t:10} -> {repair_tool_call(a, t)}')
"
```

## Known Working Endpoints

| Endpoint | Auth Method | Notes |
|----------|------------|-------|
| api.anthropic.com | Native SDK | Official endpoint |
| aiprimetech.io | Bearer + x-api-key | Both work; SDK sends both when env var is set |
| api.kie.ai/claude | Bearer only | Adapter patches this automatically |
| Azure Anthropic | Bearer + api-version | Requires query param |

## Provider Config Example

```yaml
providers:
  aiprimetech:
    api: https://aiprimetech.io
    api_mode: anthropic_messages
    key_env: AIPRIMETECH_API_KEY
    name: AI PrimeTech
    default_model: claude-opus-4-6
    models:
      - claude-opus-4-6
      - claude-opus-4-7
      - claude-sonnet-4-6
    request_timeout_seconds: 120
```
