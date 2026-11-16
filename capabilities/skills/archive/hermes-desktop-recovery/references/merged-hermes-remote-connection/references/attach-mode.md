# Attach Mode

Instead of setting up an SSH tunnel, the desktop or TUI client can attach directly to a remote dashboard via WebSocket.

## How it works

Set the environment variable `HERMES_TUI_GATEWAY_URL` to a WebSocket URL before launching the desktop app. The variable tells the client to connect to this URL instead of spawning a local gateway.

## URL format

```
ws://<host>:<port>/api/ws
```

The path `/api/ws` is mandatory — it is not `/ws`, `/`, or `/gateway`.

If the remote dashboard requires authentication, append a token parameter extracted from the dashboard HTML source or from the gateway logs.

## When to use

- No SSH access to create a tunnel
- Quick connection to a dashboard that is already running
- Testing a dashboard on a non-standard port without modifying local port bindings

## When NOT to use

- When the dashboard is behind a firewall that blocks direct WebSocket connections — use the SSH tunnel approach instead
- When the desktop app is on a different network than the server and latency is high — the tunnel provides a more reliable connection
