# Memory Pressure Without Crash Loops — Long-Uptime Exhaustion (2026-06-01)

## Context
- 23GB RAM ARM VM (Oracle Cloud, Ubuntu 24.04)
- Zero swap configured
- 3 forced reboots in one week via Oracle Cloud console

## Failure Mode (distinct from crash loops)
No service was crash-looping. All services healthy. But collectively they consumed all RAM over ~46h, leaving no buffer for the kernel.

## Services and memory at boot (~4.5GB total)
- ComfyUI (CPU mode): 568MB
- Neo4j (Java): 727MB total
- Webtop container: 1.4GB
- Qdrant: 316MB
- MiroShark: 278MB
- Hermes (gateway + TUI + services): ~600MB
- openclaw-gateway: 352MB
- Xvfb: 624MB
- Chromium: 214MB+

## Timeline
- May 30 19:51 — boot, ~4.5GB used, 0 swap
- June 1 ~18:23 — first `Under memory pressure` from systemd-journald (46h uptime)
- June 1 ~18:41 — systemd-resolved in continuous flush loop (6 flushes in 30s)
- June 1 18:43:33 — `systemd-journald: Watchdog timeout (limit 3min)!` → SIGABRT
- June 1 18:43:40 — `systemd-journald: Failed with result 'watchdog'`
- System dead. Required Oracle Cloud console manual reboot.
- 3 occurrences that week before swap was added.

## Diagnosis commands
```bash
# Count memory pressure events on previous boot
journalctl -b -1 --no-pager | grep -c "Under memory pressure"  # was 41

# Find the watchdog death
journalctl -b -1 --no-pager | grep -E "Watchdog timeout|SIGABRT|journald.*Failed"

# Check swap (empty = problem)
swapon --show
cat /proc/swaps

# Top memory consumers
ps aux --sort=-%mem | head -15
docker stats --no-stream
```

## Fix applied
```bash
fallocate -l 8G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
# Added to /etc/fstab for persistence
# Set vm.swappiness=10 (prefer RAM, swap only as safety net)
```

## Lesson
Always configure swap on VMs. With 23GB+ RAM, 8GB swap with swappiness=10 is a safety net that prevents system death without affecting normal performance. Without swap, any sustained memory growth (leak, accumulation, or just many healthy services) leads to unrecoverable crash.

## SSH port note
Also fixed SSH access: port 2222 was requested but not listening. On systemd socket activation, `Port N` in sshd_config.d has no effect — must use ssh.socket drop-in override with explicit ListenStream lines for all ports.
