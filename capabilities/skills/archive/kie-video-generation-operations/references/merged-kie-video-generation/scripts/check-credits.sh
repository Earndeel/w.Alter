#!/usr/bin/env bash
# Quick Kie.ai credit balance check
# Usage: bash scripts/check-credits.sh

set -euo pipefail

API_KEY="${KIE_API_KEY:-$(vault get kie/api_key 2>/dev/null || true)}"
if [ -z "$API_KEY" ]; then
  echo "Error: KIE_API_KEY not set and 'vault get kie/api_key' failed" >&2
  exit 1
fi

curl -s -H "Authorization: Bearer $API_KEY" \
  https://api.kie.ai/api/v1/chat/credit | jq -r '.data // empty'
