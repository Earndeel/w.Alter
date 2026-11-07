#!/bin/bash
# Quick audit of all systemd services for crash-loop risk
# Usage: bash audit-crash-loops.sh
set -euo pipefail

echo "=== Systemd Crash Loop Audit ==="
echo "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

echo "--- Failed services ---"
systemctl list-units --state=failed --no-pager --no-legend
echo ""

echo "--- Services in restart loop (activating) ---"
systemctl list-units --state=activating --type=service --no-pager --no-legend
echo ""

echo "--- High restart counts ---"
for svc in $(systemctl list-units --type=service --no-page --no-legend | awk '{print $1}'); do
  count=$(systemctl show "$svc" --property=NRestarts --value 2>/dev/null || echo "0")
  if [ "$count" -gt 100 ] 2>/dev/null; then
    echo "  WARNING: $svc has $count restarts"
  fi
done
echo ""

echo "--- Services with missing WorkingDirectory ---"
for svc in $(systemctl list-units --type=service --no-page --no-legend | awk '{print $1}'); do
  dir=$(systemctl show "$svc" --property=WorkingDirectory --value 2>/dev/null)
  if [ -n "$dir" ] && [ "$dir" != "" ] && [ ! -d "$dir" ]; then
    echo "  MISSING: $svc → $dir"
  fi
done
echo ""

echo "--- Memory status ---"
free -h
echo ""

echo "--- Journal memory pressure events (last 24h) ---"
journalctl --since "24 hours ago" --no-pager -q | grep -c "Under memory pressure" || echo "0"
echo ""

echo "--- Watchdog/timeout failures (last 24h, Pattern C) ---"
count_timeout=$(journalctl --since "24 hours ago" --no-pager -q | grep -c "start operation timed out" || echo "0")
count_watchdog=$(journalctl --since "24 hours ago" --no-pager -q | grep -c "Failed with result 'watchdog'" || echo "0")
echo "  Start timeouts: $count_timeout"
echo "  Watchdog kills: $count_watchdog"
echo ""

echo "--- Unnecessary snaps (headless servers) ---"
snap list 2>/dev/null | grep -iE "chromium|cups|gnome|gtk-common|mesa" || echo "  None found (good)"
echo ""

echo "--- Disk usage ---"
df -h / | tail -1
echo ""

echo "=== Audit complete ==="
