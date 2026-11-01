---
name: hermes-gateway-systemd-debug
description: Debug and fix hermes-gateway systemd service failures (CHDIR errors, restart loops, --replace process wars, orphaned processes, network degradation)
category: devops
---

# Hermes Gateway Systemd Debug & Fix

## Common Problem: CHDIR Exit Code 200

The `hermes-gateway.service` fails with exit code 200 and "changing to the requested working directory failed: Permission denied" in journalctl.

**Root cause**: Service runs as `ubuntu` user but `/root/.hermes` is only accessible by root.

### Symptoms
```
journalctl -u hermes-gateway.service
# Shows: "Main process exited, code=exited, status=200/CHDIR"
# Shows: "Permission denied" when trying to change to WorkingDirectory
```

### Fix

Edit `/etc/systemd/system/hermes-gateway.service`:

```ini
[Service]
User=root
Group=root
WorkingDirectory=/root/.hermes
Environment="HOME=/root"
Environment="USER=root"
Environment="LOGNAME=root"
Environment="HERMES_HOME=/root/.hermes"
Restart=on-failure
RestartSec=30
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart hermes-gateway.service
sudo systemctl status hermes-gateway.service --no-pager
```

### Verification
```bash
tail -20 ~/.hermes/logs/gateway.log
# Should show: "Connected to Telegram (polling mode)"
# Should show: "✓ telegram connected"
```

## Related: broader crash-loop recovery
For system-wide crash loops (multiple services, memory pressure, SSH lockout), see `systemd-crash-loop-recovery`.

## Problem: --replace Flag Causes Process Wars

If the systemd unit has `gateway run --replace` in ExecStart, the gateway may SIGKILL itself during startup. The `--replace` flag tells the gateway to kill any existing instance — but when systemd starts it, the process kills its own systemd-managed PID, causing immediate restart loops.

**Symptoms**:
- `systemctl status hermes-gateway` shows "activating (auto-restart)" with `signal=KILL`
- Journal shows "Shutdown context: signal=SIGTERM" within 2 seconds of startup
- Service cycles between starting and killed

**Fix**: Remove `--replace` from ExecStart:
```bash
sed -i 's/gateway run --replace/gateway run/' /etc/systemd/system/hermes-gateway.service
systemctl daemon-reload
systemctl restart hermes-gateway
```

## Problem: User-Level vs System-Level Service Conflict (3 services, 1 gateway)

After a Hermes update or manual setup, you may end up with **three** systemd services trying to run the same gateway:

| Service | Location | Notes |
|---------|----------|-------|
| `hermes-gateway.service` (user) | `~/.config/systemd/user/` | Correct — uses `--replace` |
| `hermes-agent.service` (system) | `/etc/systemd/system/` | Duplicate — no `--replace` |
| `hermes-gateway.service` (system) | `/etc/systemd/system/` | Duplicate — no `--replace` |

The system-level services start without `--replace`, see the user-level PID already running, fail with "Gateway already running (PID XXXX)", and systemd retries them in a loop until `StartRequestRepeatedTooQuickly` kicks in — wasting resources and polluting logs.

**Diagnosis**:
```bash
# Check system-level services
systemctl status hermes-agent.service hermes-gateway.service 2>&1 | grep -E "Loaded|Active"
# Check user-level service
systemctl --user status hermes-gateway.service 2>&1 | head -8
# Check if lingering is enabled (required for user service to start at boot)
loginctl show-user root 2>/dev/null | grep Linger
```

**Fix — keep only the user-level service**:
```bash
# 1. Remove system-level service files
rm /etc/systemd/system/hermes-agent.service /etc/systemd/system/hermes-gateway.service
systemctl daemon-reload

# 2. Mask them so a future update can't recreate them
systemctl mask hermes-agent.service
systemctl mask hermes-gateway.service

# 3. Enable lingering so the user service starts at boot without a login session
loginctl enable-linger root

# 4. Verify user-level service is healthy
systemctl --user status hermes-gateway.service
```

**Why mask instead of just disable?** A Hermes update that runs `gateway install` could re-enable a disabled service. Masking (symlink → `/dev/null`) makes it impossible to start, even if re-enabled.

**Verification**:
```bash
# System-level = masked (can't start)
systemctl status hermes-agent.service hermes-gateway.service | grep "masked"
# User-level = active
systemctl --user is-active hermes-gateway.service
# Linger = yes
loginctl show-user root | grep Linger
```

## Problem: Orphaned Gateway Process Outside Systemd

The gateway may be running as an orphan process (started manually or from a TUI session) while systemd shows `inactive`. This causes confusion and prevents systemd from managing the lifecycle.

**Diagnosis**:
```bash
# systemd says inactive...
systemctl is-active hermes-gateway
# ...but process is alive
ps aux | grep "[h]ermes_cli.main gateway"
```

**Fix**: Kill orphans, then let systemd manage it:
```bash
systemctl stop hermes-gateway 2>/dev/null
# Use bracket trick to avoid matching grep itself
ps aux | grep "[h]ermes_cli.main gateway" | awk '{print $2}' | xargs -r kill -9
sleep 2
systemctl enable hermes-gateway
systemctl start hermes-gateway
```

## Problem: Network Degradation (Stale Process)

A long-running gateway process can accumulate dead TCP sockets and enter a state where ALL outbound connections fail — Telegram polling, LLM API calls, everything — despite `curl` working fine from the terminal.

**Symptoms**:
- Journal shows repeated `[Telegram] Primary api.telegram.org connection failed` and fallback IP failures
- LLM API calls also fail with `APIConnectionError`
- `curl https://api.telegram.org` works from terminal (confirms VPS network is OK)
- Process has been running for days/weeks

**Root cause**: Python asyncio socket leak or DNS resolver cache corruption after extended uptime.

**Fix**: Restart the gateway process:
```bash
systemctl restart hermes-gateway
```

**Prevention**: Set up the gateway watchdog timer. See `scripts/gateway-watchdog.sh` — checks every 5 min if the gateway PID is alive, restarts cleanly if not. Deploy as a systemd user-level timer:

```ini
# ~/.config/systemd/user/gateway-watchdog.timer
[Unit]
Description=Gateway Watchdog Timer

[Timer]
OnBootSec=60
OnUnitActiveSec=300
AccuracySec=30

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/gateway-watchdog.service
[Unit]
Description=Gateway Watchdog — restart hermes-gateway if dead

[Service]
Type=oneshot
ExecStart=/root/.hermes/scripts/gateway-watchdog.sh
Environment="XDG_RUNTIME_DIR=/run/user/0"
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gateway-watchdog.timer
systemctl --user list-timers  # verify
```

## Problem: Service Masked But Gateway Actually Running (Don't Misdiagnose)

`systemctl status hermes-gateway` reports `masked` and `failed`, with timestamps days or weeks old. The instinct is to tell the user the gateway is broken — that messaging platforms (Telegram, Discord, etc.) are down. **Verify before reporting.** A masked unit and a working gateway are not contradictory: the user (or a cron, or a tmux session) may be running it manually via `hermes gateway run --replace`, and that manual process is what's serving Telegram.

### Diagnosis

```bash
# Systemd says it's dead
systemctl status hermes-gateway
# × hermes-gateway.service
#      Loaded: masked (Reason: Unit hermes-gateway.service is masked.)
#      Active: failed ... since Thu 2026-06-04

# But the gateway is alive somewhere else
ps aux | grep -E "hermes.*gateway run|hermes_cli.main gateway" | grep -v grep
# root  1659890  ... python -m hermes_cli.main gateway run --replace
```

If a `gateway run` process exists, the masked systemd unit is **deliberately masked to prevent collisions** with the manual process. Telegram, Discord, etc., are served by the manual process and work fine.

### Decision tree

| systemd unit | manual `gateway run` PID | Reality |
|---|---|---|
| active | none | Healthy, systemd-managed |
| masked/failed | running | Healthy, manual-managed (don't unmask without killing the manual process first) |
| inactive/failed | none | Actually broken — fix it |
| active | also running | Process war, collision imminent — kill one |

### Fix (when the user wants systemd back in charge)

1. Confirm with the user before changing anything — they may have masked it on purpose to keep their manual session in charge.
2. Stop the manual process: `pkill -f "hermes_cli.main gateway"` (gracefully if possible).
3. `systemctl unmask hermes-gateway && systemctl restart hermes-gateway`.
4. Check the journal for any `--replace` self-kill loop (see "--replace Flag Causes Process Wars" above).

### Pitfall — don't unmask blindly

Unmasking and restarting while a manual `gateway run` is alive will produce a "Gateway already running (PID XXXX)" exit-200 loop, then `Start request repeated too quickly`, then re-mask. You're back where you started, but with extra noise in the journal. Always check `ps aux` first.



If Telegram fails with "InvalidToken", the bot token may not be properly set:
```bash
hermes config set TELEGRAM_BOT_TOKEN "YOUR_TOKEN_HERE"
```

## Manual Gateway Test (Before Systemd)

```bash
cd /root/.hermes
/root/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run
```
