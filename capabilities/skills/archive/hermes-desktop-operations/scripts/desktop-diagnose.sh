#!/bin/bash
# Hermes Desktop redacted connectivity triage. Run on the client.
set -euo pipefail

url="${HERMES_DESKTOP_REMOTE_URL:-$(launchctl getenv HERMES_DESKTOP_REMOTE_URL 2>/dev/null || true)}"
token="${HERMES_DESKTOP_REMOTE_TOKEN:-$(launchctl getenv HERMES_DESKTOP_REMOTE_TOKEN 2>/dev/null || true)}"

pass() { printf '[PASS] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }

[[ -n "$url" ]] && pass "remote URL is set" || fail "remote URL is not set"
[[ -n "$token" ]] && pass "remote token is set" || fail "remote token is not set"

if [[ -n "$url" && -n "$token" ]]; then
  status=$(curl -sk --max-time 8 -o /dev/null -w '%{http_code}' \
    -H "X-Hermes-Session-Token: $token" "$url/api/status" || true)
  case "$status" in
    200) pass "status endpoint returned 200" ;;
    401) fail "status endpoint returned 401; inspect token scope" ;;
    000) fail "backend is unreachable; inspect relay/Tailscale" ;;
    *) warn "status endpoint returned HTTP $status" ;;
  esac
fi

if command -v pgrep >/dev/null 2>&1 && pgrep -f 'Hermes([ /]|$)' >/dev/null 2>&1; then
  pass "a Hermes process is running"
else
  warn "no matching Hermes process was found"
fi
