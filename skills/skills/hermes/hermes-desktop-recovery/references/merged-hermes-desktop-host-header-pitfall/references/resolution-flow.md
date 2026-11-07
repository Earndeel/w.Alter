# Diagnostic Resolution Flow

## Step 1 — Identify the error

The desktop app shows one of three error types. Each maps to a different root cause:

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `400: Invalid Host header` | Non-loopback Host header reaching v0.18.2+ dashboard | Switch to SSH loopback tunnel |
| `timeout` / backend not ready | SSH tunnel not established | Start the SSH tunnel |
| `connection refused` | Forwarding layer or dashboard down | Restart services |

## Step 2 — Verify from the server

Check dashboard is running and reachable:

```
systemctl --user status hermes-dashboard
ss -tlnp | grep 8787
```

Check if the SSH tunnel has established connections:

```
ss -tn | grep 8787
```

If no ESTAB connections appear, the tunnel is not active from the Mac.

## Step 3 — Fix for Host header 400

The Mac must use SSH tunnel to localhost. The launcher script should:
1. Start SSH tunnel: `ssh -L 9119:127.0.0.1:8787 <server> -N`
2. Wait for dashboard at `http://127.0.0.1:9119/api/status`
3. Write `connection.json` with `mode: remote`, `url: http://127.0.0.1:9119`
4. Launch the Electron app

## Step 4 — Fix for timeout

The SSH tunnel must be re-established. On the Mac:
1. Kill any stale SSH session to the server
2. Run the tunnel command from Step 3
3. Relaunch the desktop app (Cmd+Q first)
