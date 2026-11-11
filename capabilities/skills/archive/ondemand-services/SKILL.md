---
name: ondemand-services
description: On-demand service management — services start when needed, stop after idle
tags: [systemd, memory, watchdog, on-demand]
triggers:
  - "service on demand"
  - "ondemand"
  - "start comfyui/ollama/framelens"
  - "watchdog idle"
  - "memory optimization"
---

# On-Demand Services

> **State on 2026-11-09.** MiroShark and Neo4j were retired on 2026-11-09 (units, app, tunnel and package removed); asterisk and qdrant on 2026-10-19, Hindsight API retired. `ondemand.sh` and `ondemand-watchdog.timer` are live: run `ondemand.sh status` for the real list.

Services that are too heavy to run 24/7 are managed by `ondemand.sh`.

## When to Use

- Need to start/stop heavy services (ComfyUI, Ollama, etc.) that aren't running 24/7
- Debugging why a service isn't available or the watchdog isn't managing it
- Checking status of on-demand services or their idle timeouts

## Managed Services

| Service | Port | Idle Timeout | Dependencies |
|---------|------|-------------|--------------|
| comfyui | 8188 | 30min | none |
| ollama | 11434 | 30min | none |
| framelens | 5002 | 30min | none |

## Commands

```bash
# Status
ondemand.sh status

# Start a service (starts deps automatically)
ondemand.sh start comfyui

# Stop a service
ondemand.sh stop comfyui

# Stop all on-demand services
ondemand.sh stop-all

# Check idle (called by watchdog timer)
ondemand.sh idle
```

## How It Works

1. Services are `systemctl disable`d — they won't start at boot
2. `ondemand-watchdog.timer` runs every 2 minutes, calls `ondemand.sh idle`
3. Idle check: if a service has 0 active TCP connections for >30 min, it's stopped
4. `ondemand.sh start <name>` starts the service + dependencies, waits for port to be ready
5. Activity timestamp stored in `/run/ondemand/<name>.last`

## Always-On Services (not managed by ondemand)

- hermes-gateway
- docker (containers: hindsight-pg, webtop, flaresolverr)
- tailscaled
- cloudflared tunnels (lightweight)

## Files

- `/usr/local/bin/ondemand.sh` — main script
- `/etc/systemd/system/ondemand-watchdog.service` — watchdog oneshot
- `/etc/systemd/system/ondemand-watchdog.timer` — 2min timer
- `/run/ondemand/` — state directory (activity timestamps)

## Pitfalls

- **Don't use socket activation for these services** — tried systemd socket units (ondemand-*.socket) listening on the same port as the service, with a Python proxy receiving connections via fd3 and forwarding to the service. Failed because the service can't bind its port while the socket unit holds it. Moving the service to an internal port (e.g., 18188) and proxying from the external port works but is fragile (race conditions, extra complexity). The simple approach (disabled at boot + watchdog + manual start) is more reliable.
- Cloudflare tunnels stay always-on by default; they return 502 when the service is stopped. If Monsieur asks to truly pause ComfyUI, stop the ComfyUI tunnel too, not just the backend.
- On ARM (Oracle Cloud), ComfyUI runs on CPU (--cpu flag); slow but functional
- **Services must be stopped BEFORE disabling** — `systemctl disable` only prevents boot start, doesn't stop a running service
- **Do not broad-kill OpenClaw-looking processes** — identify the owning unit first.
- **snapd removal of unnecessary snaps** reduces system boot time and prevents snapd startup timeouts. Check `snap list` periodically — chromium, cups, gnome themes are common wastes on headless servers.
