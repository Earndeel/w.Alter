---
name: systemd-crash-loop-recovery
description: "Diagnose and recover from systemd service crash loops that cause memory pressure, journal spam, and system-wide lockouts. Covers SSH timeout, OOM, restart counter analysis, and service masking."
category: devops
tags: [systemd, debugging, memory, crash-loop, ssh, recovery]
---

# Systemd Crash Loop Recovery

## When to load
- SSH connection to server times out (`Operation timed out`)
- Server becomes unresponsive or extremely slow
- `systemd-journald: Under memory pressure, flushing caches` in logs
- Services with absurd restart counters (10k+)
- Multiple services in `activating (auto-restart)` state simultaneously
- **journald or snapd watchdog timeout** — `Failed with result 'watchdog'` or `Failed with result 'timeout'`
- **VM requires manual reboot** via cloud console (Oracle, AWS, etc.)

## Diagnosis workflow

### Step 1: Identify the boot
```bash
uptime                           # how long since reboot
who -b                           # last boot time
journalctl --list-boots | head -5 # boot history with IDs
```

### Step 2: Check for crash-looping services
```bash
# Previous boot's last logs (the crash)
journalctl -b -1 --no-pager -n 50

# Current boot errors
journalctl --since "1 hour ago" -p err --no-pager | tail -40

# Failed services right now
systemctl list-units --state=failed --no-pager

# Services stuck in restart loops
systemctl list-units --state=activating --no-pager
```

### Step 3: Identify the crash-loop offenders
Look for:
- **Restart counters > 1000** — these are the killers
- **`status=200/CHDIR`** — working directory missing
- **`status=203/EXEC`** — binary missing
- **`status=2/INVALIDARGUMENT`** — script/file missing
- **`Under memory pressure, flushing caches`** — system is drowning

```bash
# Check restart counters for suspect services
systemctl show <service> --property=NRestarts

# Check if working directories exist
for svc in <list>; do
  dir=$(systemctl show $svc --property=WorkingDirectory --value)
  echo "$svc: $dir → $([ -d "$dir" ] && echo OK || echo MISSING)"
done
```

### Step 4: Check for contributing factors
```bash
# Kernel OOM kills
dmesg | grep -iE "oom|kill|Out of memory"

# Journal memory pressure events
journalctl -b -1 --no-pager | grep -c "Under memory pressure"

# Log spam volume (rejected connections, missing files)
journalctl -b -1 --no-pager | grep -c "rejected due to acl"
journalctl -b -1 --no-pager | grep -c "No such file or directory"

# Large state files
du -sh /root/.hermes/state.db
```

## The cascade pattern

```
Missing directory/binary
  → service exits in <100ms
    → Restart=always triggers immediately
      → thousands of restarts per hour
        → journal fills with failure logs
          → systemd-journald memory pressure
            → kernel starts reclaiming memory
              → SSH daemon can't allocate
                → "Operation timed out" on client
                  → system effectively dead
```

**Timeline from real incident (2026-05-17):**
- 10 days of crash loops (156k restarts each for 5 services)
- Tolerated until journal + state.db + log spam hit critical mass
- 10:15 AM: first `Under memory pressure` warning
- 10:45 AM: snapd SIGABRT, maximum pressure
- 10:48 AM: SSH dead, system frozen
- 11:12 AM: forced reboot via Oracle console

## Fix: stop, disable, mask

### Standard fix
```bash
systemctl stop <service>.service
systemctl disable <service>.service
```

### When disable isn't enough (service keeps restarting)
```bash
# Must delete the unit file first if it exists in /etc/systemd/system/
rm /etc/systemd/system/<service>.service
systemctl daemon-reload
systemctl mask <service>.service   # creates symlink → /dev/null
```

### Verify all clear
```bash
systemctl list-units --state=failed --no-pager   # should be 0
systemctl is-active <all-suspect-services>
free -h   # memory recovering
```

## Repair: recreate missing watchdog scripts

If a watchdog script is missing (e.g., `hermes-watchdog.sh`), recreate it:

```bash
cat > /root/.hermes/hermes-watchdog.sh << 'EOF'
#!/bin/bash
set -euo pipefail
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
PIDFILE="$HERMES_HOME/gateway.pid"
LOCKFILE="$HERMES_HOME/gateway.lock"
LOGFILE="$HERMES_HOME/logs/watchdog.log"
mkdir -p "$HERMES_HOME/logs"
log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "$LOGFILE"; }
cleanup() { log "Watchdog shutting down"; rm -f "$PIDFILE" "$LOCKFILE"; }
trap cleanup EXIT
log "Watchdog starting"
while true; do
    if [ -f "$PIDFILE" ]; then
        OLD_PID=$(cat "$PIDFILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            sleep 30; continue
        else rm -f "$PIDFILE" "$LOCKFILE"; fi
    fi
    hermes gateway run --replace &
    echo $! > "$PIDFILE"
    wait $! 2>/dev/null
    rm -f "$PIDFILE" "$LOCKFILE"
    sleep 10
done
EOF
chmod +x /root/.hermes/hermes-watchdog.sh
systemctl daemon-reload
systemctl restart hermes-agent.service
```

## Prevention

### Set StartLimitBurst on all services
```ini
[Service]
StartLimitIntervalSec=600
StartLimitBurst=10
```
This stops systemd from restarting a service after 10 failures in 10 minutes.

### Audit services regularly
```bash
# Find services with high restart counts
systemctl list-units --type=service --state=failed,activating --no-pager
for svc in $(systemctl list-units --type=service --state=activating --no-page --no-legend | awk '{print $1}'); do
  count=$(systemctl show $svc --property=NRestarts --value)
  [ "$count" -gt 100 ] && echo "WARNING: $svc has $count restarts"
done
```

## Pitfalls
- **`systemctl disable` does NOT stop a running service** — always `stop` first, then `disable`
- **`systemctl mask` fails if unit file exists** in `/etc/systemd/system/` — must `rm` + `daemon-reload` first
- **Crash loops can run for DAYS** before causing visible symptoms — the system tolerates them until memory/journal pressure hits a tipping point
- **Multiple services can crash-loop simultaneously** — check ALL suspect services, not just the first one you find
- **`walter-ccr.service` (forking type)** — `ccr start` with no providers configured causes timeout-style restarts, not instant exits. Different failure mode but same memory impact.
- **Journal spam amplifies memory pressure** — each restart generates log entries, and thousands per hour fill journal buffers
- **⚠ "Under memory pressure" is MISLEADING** — journald and resolved emit this message when cgroup PSI (Pressure Stall Information) fires. It does NOT mean system RAM is full. A service with 5GB used on a 23GB machine can trigger this if disk I/O is saturated or journald is overwhelmed by log volume. Always check `free -h` and `dmesg | grep oom` BEFORE assuming memory is the cause. The real culprit is often a restart-looping service generating log spam, not actual RAM exhaustion.

## Three Distinct Failure Modes

This skill covers three patterns that cause system-wide crashes:

**Pattern A — Crash Loops** (the cascade): Service restarts thousands of times → journal spam → memory exhaustion. Fix: stop/disable/mask the looping service. See [Step 3](#step-3-identify-the-crash-loop-offenders) above.

**Pattern B — Long-Uptime Exhaustion** (no crash loops): All services healthy, but collectively consume all RAM over 24-72h. With zero swap, kernel has no buffer → journald watchdog timeout → system death. Fix: add swap. Diagnosis: `journalctl -b -1 | grep -c "Under memory pressure"` — count > 10 without crash-looping services = Pattern B.

→ See `references/incident-2026-06-01-memory-pressure-no-crashloop.md` for full timeline, diagnosis commands, and fix.

**Pattern C — Watchdog Timeout Cascade** (no crash loop, no OOM): A service fails to start within its `TimeoutStartSec`, gets killed, retries — each attempt takes the full timeout period. 14 retries × 90s = 21 minutes of restart churn. The log volume from repeated timeouts overwhelms journald, which hits its own `WatchdogSec` and gets SIGABRT'd. System becomes unstable and reboots. **RAM is not the cause** — "Under memory pressure" messages are misleading (they're cgroup PSI events, not system-wide OOM).

Diagnosis:
```bash
# Look for start timeout failures (Pattern C signature)
journalctl -b -1 --no-pager | grep "start operation timed out" | wc -l
journalctl -b -1 --no-pager | grep "Failed with result 'timeout'" | head -20

# Check restart counters during the crash window
journalctl -b -1 --no-pager | grep "restart counter is at" | tail -5

# The key differentiator from Pattern A: restarts are SLOW (90s each, not instant)
```

Fix: Add a drop-in to limit restart attempts (see `references/incident-2026-06-01-snapd-watchdog-cascade.md` for the exact commands and full timeline).

→ See `references/incident-2026-06-01-snapd-watchdog-cascade.md` for full diagnosis and fix.

## Pitfall: SSH Port Override on systemd Socket Activation

Adding `Port N` to `sshd_config.d/` does NOTHING when `ssh.socket` is active. The socket controls listened ports. Must use a drop-in override for `ssh.socket` with explicit `ListenStream=` entries for all ports, then `daemon-reload` + restart socket + restart ssh. Don't forget the firewall rule.

## Related skills
- `hermes-gateway-systemd-debug` — narrower, gateway-specific CHDIR issues
- `ssh-mac-remote-control` — SSH hardening and Tailscale setup for Mac↔VPS
