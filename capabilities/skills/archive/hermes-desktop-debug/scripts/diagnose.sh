#!/bin/bash
# Hermes V2 Desktop diagnostic script — run on macOS
# Quick triage: checks env vars, renderer bundle, and backend connectivity.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=== Hermes V2 Desktop Diagnostic ==="
echo ""

# 1. Env vars
URL=$(launchctl getenv HERMES_DESKTOP_REMOTE_URL 2>/dev/null || true)
TOKEN=$(launchctl getenv HERMES_DESKTOP_REMOTE_TOKEN 2>/dev/null || true)

if [ -z "$URL" ]; then
  fail "HERMES_DESKTOP_REMOTE_URL is not set"
else
  pass "HERMES_DESKTOP_REMOTE_URL = $URL"
fi

if [ -z "$TOKEN" ]; then
  fail "HERMES_DESKTOP_REMOTE_TOKEN is not set"
  echo "   → Fix: launchctl setenv HERMES_DESKTOP_REMOTE_TOKEN \"<token>\""
else
  pass "HERMES_DESKTOP_REMOTE_TOKEN is set"
fi

# 2. Renderer bundle
INDEX="/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/index.html"
if [ -f "$INDEX" ]; then
  pass "Renderer bundle found: $INDEX"
else
  fail "Renderer bundle MISSING: $INDEX"
  echo "   → Fix: rebuild with 'hermes desktop --force-build' and reinstall .app"
fi

# 3. Backend connectivity (only if URL and TOKEN are set)
if [ -n "$URL" ] && [ -n "$TOKEN" ]; then
  echo ""
  echo "--- Backend connectivity ---"
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" \
    -H "X-Hermes-Session-Token: $TOKEN" \
    "$URL/api/status" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    pass "Backend /api/status returns 200"
  elif [ "$HTTP_CODE" = "401" ]; then
    fail "Backend returns 401 — token mismatch or not accepted"
  elif [ "$HTTP_CODE" = "000" ]; then
    fail "Backend unreachable — check Tailscale and 'tailscale serve' on server"
  else
    warn "Backend returned HTTP $HTTP_CODE"
  fi

  # Check assets
  ASSET_CODE=$(curl -sk -o /dev/null -w "%{http_code}" \
    "$URL/assets/index-WrAtZQWO.js" 2>/dev/null || echo "000")
  if [ "$ASSET_CODE" = "200" ]; then
    pass "JS assets reachable (200)"
  else
    warn "JS assets returned $ASSET_CODE — may cause blank screen"
  fi
fi

# 4. App process check
echo ""
echo "--- App process ---"
if pgrep -f "Hermes V2" > /dev/null 2>&1; then
  pass "Hermes V2 process is running"
else
  warn "Hermes V2 is not running"
fi

echo ""
echo "=== Diagnostic complete ==="
