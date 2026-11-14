# Higgsfield MCP OAuth on headless Hermes hosts

## Symptom cluster

- Hosted MCP endpoint: `https://mcp.higgsfield.ai/mcp`.
- OAuth authorization may fail with `redirect_uri mismatch` when Hermes emits `http://127.0.0.1:<port>/callback`.
- Retrying with a stale browser redirect creates `State parameter mismatch` because each retry rotates `state` and PKCE `code_challenge`.
- `hermes mcp login <server>` can time out around 40s if the login path does not pass the server's `connect_timeout` into `_probe_single_server`.

## Working pattern

Config shape:

```yaml
mcp_servers:
  higgsfield:
    url: https://mcp.higgsfield.ai/mcp
    auth: oauth
    enabled: true
    timeout: 180
    connect_timeout: 600
    oauth:
      timeout: 600
      redirect_host: localhost
```

If Hermes lacks `oauth.redirect_host` support, patch the OAuth metadata/registration builder to use `cfg.get("redirect_host", "127.0.0.1")` for callback URLs, or otherwise make the authorization URL and dynamic client registration use `localhost` consistently.

If the CLI login path ignores `connect_timeout`, patch `_reauth_oauth_server()` so it calls:

```python
connect_timeout = float(server_config.get("connect_timeout") or 300)
tools = _probe_single_server(name, server_config, connect_timeout=connect_timeout)
```

## Manual callback delivery

When the user sends a final redirect URL and `process.submit` cannot write to stdin, hit the listener from the Hermes host:

```bash
curl -sS 'http://localhost:<port>/callback?code=...&state=...' -i
```

Expect `Authorization Successful`, then wait/poll the login process. Do not reuse the URL after a failed attempt; request the newest authorization URL.

## Verification used

Run from the Hermes repo venv, not system Python if pytest plugins differ:

```bash
cd /root/.hermes/hermes-agent
venv/bin/python -m py_compile hermes_cli/mcp_config.py tools/mcp_oauth.py
venv/bin/python -m pytest \
  tests/tools/test_mcp_oauth_manager.py \
  tests/tools/test_mcp_oauth_integration.py \
  tests/tools/test_mcp_oauth_cold_load_expiry.py \
  -q -o 'addopts='
```

Expected targeted evidence in this case: `30 passed`.
