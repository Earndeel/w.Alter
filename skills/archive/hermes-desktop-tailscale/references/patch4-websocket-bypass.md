# Patch 4: WebSocket auth bypass — exact code

## Location

`hermes_cli/web_server.py`, function `_ws_auth_reason`, **after** the `auth_required` gate block (the `return "ticket_invalid", "ticket"` line) and **before** the legacy `token = ws.query_params.get("token", "")` line.

## Old code (the line to replace)

```python
    token = ws.query_params.get("token", "")
    if not token:
        return "no_credential", "none"
    if hmac.compare_digest(token.encode(), _SESSION_TOKEN.encode()):
        return None, "token"
    return "token_mismatch", "token"
```

## New code

```python
    # Bypass token auth for Tailscale-trusted hosts — same logic as HTTP layer
    host_header = ws.headers.get("host", "")
    bound_host = getattr(app.state, "bound_host", None)
    if host_header and _is_accepted_host(host_header, bound_host):
        return None, "trusted_host"

    token = ws.query_params.get("token", "")
    if not token:
        return "no_credential", "none"
    if hmac.compare_digest(token.encode(), _SESSION_TOKEN.encode()):
        return None, "token"
    return "token_mismatch", "token"
```

## Verification

After restart, test with Python websockets:

```python
import asyncio, websockets

async def test():
    try:
        async with websockets.connect(
            'ws://127.0.0.1:8787/api/ws',
            additional_headers={'Host': '100.91.35.121:9119'},
            ping_interval=None
        ) as ws:
            print('WebSocket CONNECTED')
            await ws.close()
    except websockets.exceptions.InvalidStatus as e:
        print(f'FAILED: HTTP {e.response.status_code}')  # 403 = Patch 4 missing

asyncio.run(test())
```

## Why it's separate from HTTP patches

`_ws_auth_reason` handles WebSocket upgrade authentication. It runs inside the `@app.websocket("/api/ws")` handler, which Starlette routes to directly for WebSocket upgrades — the HTTP middleware chain (`auth_middleware`, `_require_token`) does NOT apply to WebSocket connections. Patches 2+3 only cover HTTP routes. Patch 4 covers the WebSocket route.
