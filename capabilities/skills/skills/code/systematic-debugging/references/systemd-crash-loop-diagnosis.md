# Systemd Crash Loop Diagnosis — Server Unresponsive

## When to Use

SSH timeout / server unresponsive / "Operation timed out" on port 22.
No OOM kill in dmesg, but server was rebooted or had to be force-rebooted.

## Diagnostic Checklist (in order)

### 1. Confirm reboot + uptime

```bash
uptime && who -b && last reboot | head -5
```

### 2. Check journalctl from CURRENT boot for errors

```bash
journalctl --since "10 min ago" -p err --no-pager | tail -40
```

Look for:
- `"Under memory pressure, flushing caches"` — system was starved
- `"Changing to the requested working directory failed"` — service dir missing
- `"Scheduled restart job, restart counter is at NNNNN"` — **crash loop** (high N = bad)

### 3. Check dmesg for kernel-level causes

```bash
dmesg | grep -iE "oom|kill|panic|error|fail|memory" | tail -20
```

- OOM killer entries → memory exhaustion
- No OOM but memory pressure logs → slow death, not sudden kill

### 4. Check previous boot's last logs

```bash
journalctl -b -1 --no-pager -n 50
```

This reveals what was happening RIGHT BEFORE the crash/reboot.

### 5. Identify ALL crash-looping services (not just failed ones)

`systemctl list-units --state=failed` only shows services that gave up restarting.
Active crash-loopers show as `activating (auto-restart)` and won't appear there.

```bash
# Services that gave up
systemctl list-units --state=failed --no-pager

# Services STILL crash-looping (activating state)
systemctl list-units --state=activating --no-pager

# Nuclear option: find all services with high restart counts
systemctl list-units --type=service --no-pager -a | grep -oP '^\S+' | while read svc; do
  count=$(systemctl show "$svc" -p NRestarts --value 2>/dev/null)
  [ "$count" -gt 100 ] 2>/dev/null && echo "RESTARTS=$count $svc"
done | sort -t= -k2 -rn
```

**Red flags:**
- `activating (auto-restart)` in a tight loop
- Restart counter > 1000
- `status=200/CHDIR` — WorkingDirectory doesn't exist
- `status=203/EXEC` — ExecStart binary doesn't exist

### 6. Verify WorkingDirectory existence for each failing service

```bash
systemctl cat <service>.service | grep WorkingDirectory
# Then check if that dir exists
ls -la <path>
```

## Root Cause Pattern

```
Service has Restart=always + missing WorkingDirectory
  → starts, fails instantly (exit 200/CHDIR)
  → systemd restarts immediately
  → loop runs thousands of times per minute
  → each restart consumes memory (log buffers, process table entries)
  → systemd-journald flushes caches under pressure
  → system becomes unresponsive
  → SSH times out
```

Restart counters of **150,000+** have been observed in ~10 days of uptime.

### Multi-Service Cascade (common pattern)

Rarely is ONE service the sole cause. Typically 4-6 services crash-loop simultaneously,
each contributing memory pressure. The cumulative effect is what kills the server.

**Always check ALL services, not just the obvious ones:**

```bash
# Find ALL services with high restart counts
systemctl list-units --type=service --no-pager | while read line; do
  svc=$(echo "$line" | awk '{print $1}')
  [ -z "$svc" ] && continue
  count=$(systemctl show "$svc" -p NRestarts --value 2>/dev/null)
  [ "$count" -gt 0 ] 2>/dev/null && echo "$count $svc"
done | sort -rn | head -20
```

**Hidden crash-loopers to check:**
- `walter-ccr.service` (Claude Code Router) — `Type=forking`, times out instead of CHDIR
- `pipeline-dashboard.service` — script file missing (not dir)
- Any service with `Restart=always` and `RestartSec=5` (tight loop)

### Ancillary Log Spam (amplifiers, not root cause)

These don't cause the crash but amplify memory/journal pressure:

| Source | Symptom | Count to check |
|--------|---------|----------------|
| Tailscale ACL rejections | `open-conn-track: flow ... rejected due to acl` | `grep -c "rejected due to acl"` |
| Oracle metadata endpoint | `169.254.169.254` timeouts via Tailscale | Tailscale + monitoring agent |
| Missing file attempts | `can't open file` repeated every 5s | `grep -c "can't open file"` |
| snapd | SIGABRT crash under memory pressure | Check `journalctl -u snapd` |

```bash
# Count log spam from previous boot
journalctl -b -1 --no-pager | grep -c "rejected due to acl"
journalctl -b -1 --no-pager | grep -c "can't open file"
```

### Cascade Timeline Pattern

The crash follows a predictable arc:
1. **Hours before**: crash-looping services run normally (system handles the load)
2. **~30 min before**: first `Under memory pressure, flushing caches` from journald/resolved
3. **~10 min before**: pressure messages every few seconds, other services start timing out
4. **~2 min before**: snapd or other daemon crashes (SIGABRT), SSH begins dropping
5. **Crash**: system unresponsive, SSH timeout on port 22

## Fix Procedure

### Immediate: stop the bleeding

```bash
# Stop all crash-looping services NOW
systemctl stop <service1> <service2> ...

# Disable them so they don't restart on next boot
systemctl disable <service1> <service2> ...
```

### Triage: decide per service

| Situation | Action |
|-----------|--------|
| WorkingDirectory missing, service not needed | `systemctl disable` + leave it |
| WorkingDirectory missing, service IS needed | Recreate dir, fix deps, re-enable |
| ExecStart binary missing | Same as above |
| Service crashes for other reason | Investigate root cause separately |

### Recreate missing watchdog scripts

If a watchdog/monitoring script is missing (e.g., `hermes-watchdog.sh`):

```bash
# Recreate with proper error handling
cat > /path/to/watchdog.sh << 'EOF'
#!/bin/bash
set -euo pipefail
# ... watchdog logic ...
EOF
chmod +x /path/to/watchdog.sh

# Reload and restart
systemctl daemon-reload
systemctl restart <service>
```

### Stubborn services: mask them

If `systemctl disable` isn't enough (service keeps restarting because it's already running):

```bash
# Remove unit file, then mask (symlink to /dev/null)
rm /etc/systemd/system/<service>.service
systemctl daemon-reload
systemctl mask <service>.service
```

### Verify cleanup

```bash
# No failed services
systemctl list-units --state=failed --no-pager

# Memory stable
free -h

# Crash-looping services actually stopped
systemctl is-active <service1> <service2> ...
```

## Key Signals Summary

| Signal | Meaning |
|--------|---------|
| `Under memory pressure, flushing caches` | System was memory-starved |
| Restart counter > 10000 | Service was crash-looping for hours/days |
| `status=200/CHDIR` | WorkingDirectory doesn't exist |
| `status=203/EXEC` | ExecStart binary doesn't exist |
| `Operation timed out` on SSH | sshd couldn't accept connections (resource exhaustion) |
| No OOM in dmesg | Slow death, not sudden kill |
