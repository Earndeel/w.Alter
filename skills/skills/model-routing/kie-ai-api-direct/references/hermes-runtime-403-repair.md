# Kie.ai Hermes runtime 403 repair

Validated 2026-06-29 on Hermes v0.17.0.

## Symptom

Direct Kie.ai Claude call works, but Hermes runtime fails:

- direct `https://api.kie.ai/claude/v1/messages` returns HTTP 200
- `hermes chat --provider kie --model claude-opus-4-8 ... -v` logs `HTTP 403: Your request was blocked`
- Hermes then activates fallback, e.g. Nvidia/Kimi, so the final answer may look successful

This is not a Kie credit problem when `/api/v1/chat/credit` is positive and direct Claude returns 200.

## Cause

Hermes' Anthropic adapter may build the Kie client like a generic third-party Anthropic endpoint:

- wrong auth mode risk: `x-api-key` instead of `Authorization: Bearer`
- missing browser-like `User-Agent`, causing Cloudflare 403

Direct curl/Python works because it sends Bearer auth plus browser UA. The Hermes SDK path must do the same.

## Patch pattern

File: `agent/anthropic_adapter.py`

1. Add a Kie endpoint detector after URL normalization helpers:

```python
def _is_kie_anthropic_endpoint(base_url: str | None) -> bool:
    normalized = _normalize_base_url_text(base_url)
    if not normalized:
        return False
    return normalized.rstrip("/").lower().startswith("https://api.kie.ai/claude")
```

2. Include it in `_requires_bearer_auth(...)`:

```python
return (
    normalized.startswith(("https://api.minimax.io/anthropic", "https://api.minimaxi.com/anthropic"))
    or "azure.com" in normalized
    or _is_kie_anthropic_endpoint(normalized)
)
```

3. In `build_anthropic_client(...)`, inside the Bearer-auth branch, merge a browser UA for Kie:

```python
kwargs["auth_token"] = api_key
if common_betas:
    kwargs["default_headers"] = {"anthropic-beta": ",".join(common_betas)}
if _is_kie_anthropic_endpoint(normalized_base_url):
    headers = dict(kwargs.get("default_headers") or {})
    headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    kwargs["default_headers"] = headers
```

Use `kwargs: Dict[str, Any]` if static typing otherwise infers the dict as only containing `Timeout`.

## Regression tests

File: `tests/agent/test_anthropic_adapter.py`, class `TestBuildAnthropicClient`:

- Kie base URL sets `auth_token`
- Kie base URL does not set `api_key`
- Kie headers include `User-Agent` starting with `Mozilla/5.0`
- `anthropic-beta` remains present
- trailing `/v1` is stripped before detection and still uses Bearer + UA

Run:

```bash
cd /root/.hermes/hermes-agent
source venv/bin/activate
python -m pytest tests/agent/test_anthropic_adapter.py::TestBuildAnthropicClient -q -o 'addopts='
python -m pytest tests/agent/test_auxiliary_client_anthropic_custom.py tests/run_agent/test_anthropic_third_party_oauth_guard.py -q -o 'addopts='
```

## Real verification

```bash
hermes chat --provider kie --model claude-opus-4-8 -q 'Reply exactly KIE_PATCHED_OK' -Q -v
```

Require logs to show:

- `POST https://api.kie.ai/claude/v1/messages "200 OK"`
- response model `claude-opus-4-8`
- no fallback activation

Then inspect `state.db` with Python sqlite3:

```python
import sqlite3
sid = 'SESSION_ID'
con = sqlite3.connect('/root/.hermes/state.db')
con.row_factory = sqlite3.Row
row = con.execute('select * from sessions where id=?', (sid,)).fetchone()
print(row['model'], row['billing_provider'], row['billing_base_url'])
```

Expected:

- `model = claude-opus-4-8`
- `billing_provider = custom`
- `billing_base_url = https://api.kie.ai/claude`

If billing points to Nvidia/OpenRouter/etc., the visible response was fallback, not Kie. Admirably treacherous, as fallbacks tend to be.

## GPT Responses provider (validated 2026-07-10)

Kie's GPT endpoint is a separate OpenAI Responses-compatible route:

- base URL: `https://api.kie.ai/codex/v1`
- endpoint used by the SDK: `/responses`
- model: `gpt-5-6-luna`
- key env: `KIE_API_KEY`
- transport: `codex_responses`

Requirements in Hermes:

1. Register a `ProviderProfile` named `kie-gpt` with `api_mode="codex_responses"`, the Kie base URL, `KIE_API_KEY`, and a browser-like `User-Agent` in `default_headers`.
2. Ensure `hermes_cli.runtime_provider._resolve_runtime_from_pool_entry()` honors the matching plugin profile's `api_mode`. Named API-key plugins are auto-added to `PROVIDER_REGISTRY`; without this bridge they silently fall back to `chat_completions` and Hermes reports an empty malformed stream.
3. Only trust a profile transport when the resolved URL still matches the profile base URL. Explicit endpoint overrides must retain priority: configured mode, URL detection, then matching profile mode.
4. Detect `api.kie.ai` in the Responses transport and translate Hermes reasoning effort `xhigh` to Kie's strongest tier `max`.
5. Preserve the complete Hermes function-tool list. Kie supports normal Responses function calls; do not filter to the first tool merely because a minimal connectivity probe used one tool.

### Unified Desktop provider aliases: apply the UA by host

A Desktop picker may display one umbrella provider such as `Kie.ai` while internally routing GPT Responses through `kie-gpt`, a custom provider, or another alias. A provider-slug-only header rule is therefore brittle: the correct model and endpoint can be selected while the browser UA is silently omitted, producing `HTTP 403: Your request was blocked` in a fresh session.

Apply the Kie browser UA whenever the normalized base URL host is exactly `api.kie.ai`, independent of the provider slug. Cover both OpenAI client-construction paths:

1. `agent/agent_init.py` — initial `client_kwargs` construction for a newly created agent/session.
2. `run_agent.py`, `_apply_client_headers_for_base_url(...)` — credential refreshes and client rebuilds.

Use the existing host-matching helper rather than substring matching, and preserve user-configured header overrides. A fix only in the refresh/rebuild path does **not** repair newly created sessions; a fix only in initialization can regress after credential rotation.

Verification sequence:

1. Reproduce the direct endpoint with the SDK default UA and with a browser UA; confirm the first is blocked and the second is accepted.
2. Instantiate the real `AIAgent` with the Kie Codex base URL and inspect `_client_kwargs.default_headers.User-Agent` without printing the API key.
3. Make one real no-fallback Responses call and require that it is accepted by Kie.
4. Run the Kie provider regression suite.
5. Test from a newly created Desktop session, because an already-running worker retains imported Python code.

A successful HTTP acceptance is enough to prove the 403 transport fix even if Kie's SDK wrapper returns a nonstandard response object; validate response parsing separately rather than conflating it with Cloudflare access.

Configure the saved provider with scalar `hermes config set` calls, not one JSON object. The CLI stores an object argument as a YAML string rather than a mapping:

```bash
hermes config set providers.kie-gpt.api https://api.kie.ai/codex/v1
hermes config set providers.kie-gpt.api_mode codex_responses
hermes config set providers.kie-gpt.default_model gpt-5-6-luna
hermes config set providers.kie-gpt.key_env KIE_API_KEY
```

Verify the resolver before a billable call:

```python
from hermes_cli.runtime_provider import resolve_runtime_provider
r = resolve_runtime_provider(requested="kie-gpt", target_model="gpt-5-6-luna")
assert r["api_mode"] == "codex_responses"
assert r["base_url"] == "https://api.kie.ai/codex/v1"
```

Real no-fallback tool smoke:

```bash
hermes --provider kie-gpt -m gpt-5-6-luna -t terminal,file \
  --usage-file /tmp/kie-usage.json -z \
  'Use read_file on /tmp/kie-smoke.txt and terminal to run: printf TERMINAL_OK'
```

The usage report must show `provider: kie-gpt`, `model: gpt-5-6-luna`, `completed: true`, and `failed: false`. Query the session's `messages.tool_calls` and `messages.tool_name` columns to confirm both assistant requests and tool-result rows; do not infer tool execution only from the final prose.
