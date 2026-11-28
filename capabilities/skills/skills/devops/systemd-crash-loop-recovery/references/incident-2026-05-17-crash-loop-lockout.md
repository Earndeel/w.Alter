# Incident: 2026-05-17 Server Lockout

## Timeline
- **Uptime before crash**: 10 days (since May 7, 22:49)
- **8:00 AM**: `walter-ccr.service` begins timeout loop (no providers configured)
- **10:15 AM**: First `systemd-resolved: Under memory pressure, flushing caches`
- **10:45 AM**: `snapd` crashes with SIGABRT; memory pressure peaks
- **10:48 AM**: SSH port 22 times out; system frozen
- **11:12 AM**: Forced reboot via Oracle Cloud console

## Crash-looping services

| Service | Restarts | Root cause |
|---|---|---|
| walter-litellm | 156,383 | WorkingDirectory `/root/.walter-litellm` missing |
| walter-router | 156,382 | Depends on litellm (dir missing) |
| hermes-workspace-ui | 156,380 | WorkingDirectory `/root/hermes-workspace` missing |
| pipeline-dashboard | 156,187 | `/root/projects/ad-video-pipeline/dashboard.py` missing |
| walter-ccproxy | 80,210 | WorkingDirectory `/root/.walter-ccproxy/assets` missing |
| walter-ccr | 8,169 | `ccr start` timeout — no providers configured |

## Contributing factors
- `state.db`: 625 MB (Hermes gateway loads into memory)
- 2,370 Tailscale ACL rejections to Oracle metadata endpoint (169.254.169.254)
- 1,751 failed attempts to open missing `dashboard.py`
- `unified-monitoring-agent` (Oracle Cloud) retry loops on metadata endpoint

## Resolution
1. All 6 services stopped + disabled
2. `walter-ccr` masked (unit file → /dev/null)
3. `hermes-watchdog.sh` recreated (was missing)
4. `hermes-agent.service` restarted successfully
5. Zero failed services post-fix

## Lessons
- Services were crash-looping for **10 days** before causing visible symptoms
- System tolerated ~15k restarts/day/service until journal + memory pressure hit tipping point
- `snapd` SIGABRT was a **symptom** of memory pressure, not a cause
- Oracle Cloud metadata endpoint (169.254.169.254) should be in Tailscale ACL allowlist or services should not route through Tailscale to reach it
