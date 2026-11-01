"""
Notion API — paginated query helper.

Usage:
  python3 ~/.hermes/skills/productivity/notion/scripts/notion_paginated_query.py \
    data_sources/{data_source_id}/query '{"filter": {"property": "Fai", "checkbox": {"equals": true}}}'

  python3 ~/.hermes/skills/productivity/notion/scripts/notion_paginated_query.py \
    search '{"query": "consommable"}'

Automatically paginates until next_cursor is null. Prints raw JSON to stdout.
"""
import json, urllib.request, sys, os

KEY = os.environ.get("NOTION_API_KEY", "")
if not KEY:
    # Try loading from .env
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("NOTION_API_KEY=") and not line.startswith("#") and ":" not in line[:10]:
                    KEY = line.split("=", 1)[1].strip()
                    break

if not KEY:
    print("ERROR: NOTION_API_KEY not set in environment or .env", file=sys.stderr)
    sys.exit(1)

if len(sys.argv) < 2:
    print("Usage: {} <endpoint> [filter_json]".format(sys.argv[0]), file=sys.stderr)
    sys.exit(1)

endpoint = sys.argv[1]
body = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

BASE = "https://api.notion.com/v1"
all_results = []
cursor = None

while True:
    payload = dict(body)
    if cursor:
        payload["start_cursor"] = cursor
    if not payload.get("page_size"):
        payload["page_size"] = 100
    
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {KEY}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json"
        }
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    results = resp.get("results", [])
    all_results.extend(results)
    
    cursor = resp.get("next_cursor")
    if not cursor:
        break

# Output
output = {"object": "list", "results": all_results, "total": len(all_results)}
print(json.dumps(output, indent=2, ensure_ascii=False))
