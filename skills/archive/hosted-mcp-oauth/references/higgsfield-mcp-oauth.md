# Higgsfield hosted MCP OAuth incident recipe

## Symptom

Connecting `https://mcp.higgsfield.ai/mcp` via hosted HTTP MCP OAuth from a headless/SSH Hermes host can fail in several misleading ways:

- mcporter discovery reports `Invalid scope requested`.
- Browser authorization returns `redirect_uri does not match any of the OAuth 2.0 Client's pre-registered redirect urls`.
- The login process times out while waiting for a callback, even though the user says they completed login.
- Old login processes keep printing stale authorization URLs.

## Durable fix pattern

1. Use Hermes native MCP OAuth, not mcporter, for the persistent connection.
2. Configure Higgsfield with long human-login timeouts and `oauth.redirect_host: localhost`.
3. Delete stale cached Higgsfield OAuth client/token files before retrying after changing redirect host or callback metadata.
4. Start login in a real/pseudo TTY and keep the process alive while the user authenticates.
5. On a remote host, ask for the final callback URL from the browser address bar (`http://localhost:<port>/callback?code=...&state=...`) and paste/submit it into the waiting login process.
6. Verify with `hermes mcp test higgsfield`, then reload MCP or start a new Hermes session.

## Hermes code/config quirk observed

Some Hermes versions build MCP OAuth redirect URIs with `127.0.0.1`. If a hosted provider only registered/allows `localhost`, add or patch support for an OAuth config key such as `redirect_host: localhost` and use that host consistently when building client metadata and pre-registered client info.

## Test pattern after code changes

From the Hermes repo, use the repo virtualenv:

```bash
venv/bin/python -m py_compile tools/mcp_oauth.py
venv/bin/python -m pytest tests/tools/test_mcp_oauth_manager.py tests/tools/test_mcp_oauth_integration.py tests/tools/test_mcp_oauth_cold_load_expiry.py -q -o 'addopts='
```

System Python may lack async pytest plugins; failures from that environment are not evidence that the OAuth patch is broken.
