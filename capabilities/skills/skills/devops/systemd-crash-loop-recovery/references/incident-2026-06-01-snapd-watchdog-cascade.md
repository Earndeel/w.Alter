# Incident: Snapd Watchdog Timeout Cascade (2026-06-01)

## Summary
VM w-alter (Oracle Cloud ARM64, 23GB RAM) crashed 3 times in as many days. Each crash required manual reboot via Oracle Cloud console. Initial diagnosis pointed to memory pressure (wrong). Root cause was snapd failing to start within its timeout, retrying 14 times over 21 minutes, overwhelming journald.

## Timeline (last boot before crash)
| Time | Event |
|------|-------|
| May 30 19:51 | System boot |
| Jun 01 18:11 | `snapd.service: Watchdog timeout (limit 5min)!` — first snapd failure |
| Jun 01 18:15 | `snapd.service: Failed with result 'timeout'` — restart counter at 1 |
| Jun 01 18:15-18:33 | **14 consecutive start-operation-timeout failures** (~90s each) |
| Jun 01 18:35 | snapd finally starts (adjusting startup timeout by 1m25s due to 5 snaps) |
| Jun 01 18:38 | journald "Under memory pressure, flushing caches" |
| Jun 01 18:43 | `systemd-journald.service: Watchdog timeout (limit 3min)!` → SIGABRT |
| Jun 01 18:43 | System becomes unstable, sessions die |
| Manual reboot | Via Oracle Cloud console |

## Key Evidence
- **17 snapd failures** in journal from previous boot
- **41 "memory pressure" events** — misleading, not actual OOM
- **0 kernel OOM kills** — `dmesg | grep oom` returned nothing
- **5GB used / 23GB total RAM** — well within limits
- **0 swap** — no buffer for I/O pressure spikes
- **2.9GB journal** — unbounded growth contributed to journald slowness
- **Installed snaps**: chromium, cups, gnome-46-2404, gtk-common-themes, mesa-2404 (all unnecessary on headless server)

## Root Cause
snapd startup timeout was 90s (default). With 5 heavy snaps installed (chromium, cups, gnome, gtk, mesa), the pessimistic startup estimate was 1m25s. On ARM64 with slow I/O, snapd exceeded its timeout repeatedly. Each failure generated a full restart cycle (~90s). 14 cycles = 21 minutes of continuous log generation, which overwhelmed journald's ability to flush to disk, causing its own watchdog to fire.

## Fixes Applied
1. **snapd restart limited**: `StartLimitIntervalSec=300, StartLimitBurst=3` drop-in
2. **Unnecessary snaps removed**: chromium, cups, gnome-46-2404, gtk-common-themes, mesa-2404
3. **snapd startup time**: dropped from 90s+timeout to 3.3s
4. **journald watchdog**: increased from 3min to 5min
5. **Journal capped**: `SystemMaxUse=500M` (was unbounded at 2.9GB)
6. **Swap 8GB**: added as safety net (not the root cause, but prevents Pattern B)

## Diagnostic Lesson
"Under memory pressure, flushing caches" in journald does NOT mean system RAM is full. It's triggered by cgroup PSI events — which can fire from I/O saturation, journal backlog, or cgroup-level resource contention. Always verify with `free -h` and `dmesg | grep oom` before assuming memory is the problem.
