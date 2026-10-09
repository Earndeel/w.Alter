---
name: notion
description: "Notion API via curl: pages, databases, blocks, search."
version: 1.0.0
author: community
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Notion, Productivity, Notes, Database, API]
    homepage: https://developers.notion.com
prerequisites:
  env_vars: [NOTION_API_KEY]
---

# Notion API

Use the Notion API via curl to create, read, update pages, databases (data sources), and blocks. No extra tools needed — just curl and a Notion API key.

## Prerequisites

1. Create an integration at https://notion.so/my-integrations
2. Copy the API key (starts with `ntn_` or `secret_`)
3. Store it in `~/.hermes/.env`:
   ```
   NOTION_API_KEY=ntn_your_key_here
   ```
4. **Important:** Share target pages/databases with your integration in Notion (click "..." → "Connect to" → your integration name)

## API Basics

All requests use this pattern:

```bash
curl -s -X GET "https://api.notion.com/v1/..." \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json"
```

The `Notion-Version` header is required. This skill uses `2025-09-03` (latest). In this version, databases are called "data sources" in the API.

## Common Operations

### Search

```bash
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"query": "page title"}'
```

### Get Page

```bash
curl -s "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03"
```

### Get Page Content (blocks)

```bash
curl -s "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03"
```

### Create Page in a Database

```bash
curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "xxx"},
    "properties": {
      "Name": {"title": [{"text": {"content": "New Item"}}]},
      "Status": {"select": {"name": "Todo"}}
    }
  }'
```

### Query a Database

```bash
curl -s -X POST "https://api.notion.com/v1/data_sources/{data_source_id}/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {"property": "Status", "select": {"equals": "Active"}},
    "sorts": [{"property": "Date", "direction": "descending"}]
  }'
```

### Create a Database

```bash
curl -s -X POST "https://api.notion.com/v1/data_sources" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"page_id": "xxx"},
    "title": [{"text": {"content": "My Database"}}],
    "properties": {
      "Name": {"title": {}},
      "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}},
      "Date": {"date": {}}
    }
  }'
```

### Update Page Properties

```bash
curl -s -X PATCH "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"Status": {"select": {"name": "Done"}}}}'
```

### Add Content to a Page

```bash
curl -s -X PATCH "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Hello from Hermes!"}}]}}
    ]
  }'
```

## Property Types

Common property formats for database items:

- **Title:** `{"title": [{"text": {"content": "..."}}]}`
- **Rich text:** `{"rich_text": [{"text": {"content": "..."}}]}`
- **Select:** `{"select": {"name": "Option"}}`
- **Multi-select:** `{"multi_select": [{"name": "A"}, {"name": "B"}]}`
- **Date:** `{"date": {"start": "2026-01-15", "end": "2026-01-16"}}`
- **Checkbox:** `{"checkbox": true}`
- **Number:** `{"number": 42}`
- **URL:** `{"url": "https://..."}`
- **Email:** `{"email": "user@example.com"}`
- **Relation:** `{"relation": [{"id": "page_id"}]}`

## Key Differences in API Version 2025-09-03

- **Databases → Data Sources:** Use `/data_sources/` endpoints for queries and retrieval
- **Two IDs:** Each database has both a `database_id` and a `data_source_id`
  - Use `database_id` when creating pages (`parent: {"database_id": "..."}`)
  - Use `data_source_id` when querying (`POST /v1/data_sources/{id}/query`)
- **Search results:** Databases return as `"object": "data_source"` with their `data_source_id`

## Pagination (MANDATORY)

**EVERY paginated endpoint (search, database query, list blocks) MUST be paginated until `next_cursor` is null.** The default page_size (100) never covers all items. Bases can have 180+ entries — skipping pagination silently loses data.

Use Python for pagination (avoids jq issues with accented keys and complex loops):

```python
import json, urllib.request

KEY = os.environ.get("NOTION_API_KEY", "")
BASE = "https://api.notion.com/v1"

def paginated_query(endpoint, body=None):
    """Query with automatic pagination. Returns all results."""
    all_results = []
    cursor = None
    while True:
        payload = body or {}
        if cursor:
            payload["start_cursor"] = cursor
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
        all_results.extend(resp.get("results", []))
        cursor = resp.get("next_cursor")
        if not cursor:
            break
    return all_results

# Example: query all items from a database
items = paginated_query(
    "/data_sources/{data_source_id}/query",
    {"filter": {"property": "Status", "checkbox": {"equals": False}}, "page_size": 100}
)
print(f"Total items: {len(items)}")
```

**For curl:** use `jq -r '.next_cursor // empty'` to check if more pages exist, then loop.

## Troubleshooting

### API key becomes invalid (401)

Keys can expire or get invalidated. If you get `401 unauthorized`:
1. Check the key is loaded: `grep NOTION_API_KEY ~/.hermes/.env`
2. The `.env` can get corrupted with line-number prefixes (e.g. `334:361|NOTION_API_KEY=...`) from previous tool calls bleeding into file edits. If the grep shows garbled lines, delete them and rewrite cleanly.
3. Check the vault as backup: `vault get notion/api_key`
3. Always test immediately after writing a key: `curl -s -X POST .../v1/search -d '{"page_size":1}' | jq '.object'` — should return `"list"`, not `"error"`.

### .env file corruption

Previous tool calls (read_file output like line numbers) can bleed into `.env`, adding prefixes like `334:361|` before entries. Clean with:
```bash
grep -n "NOTION_API_KEY" ~/.hermes/.env   # spot corrupted lines
sed -i '/:.*NOTION_API_KEY/d' ~/.hermes/.env  # remove broken lines
echo 'NOTION_API_KEY=ntn_your_key' >> ~/.hermes/.env
```

### jq fails on non-ASCII property names

Notion property names like `Durée`, `Fait`, `Création` cause jq parse errors (alternative operator `//` breaks on `é`). When querying pages with accented property names, use Python instead of jq:

```bash
python3 -c "
import json, urllib.request
resp = urllib.request.urlopen(urllib.request.Request(
    'https://api.notion.com/v1/search',
    data=json.dumps({'page_size': 5}).encode(),
    headers={'Authorization': 'Bearer $NOTION_API_KEY', 'Notion-Version': '2025-09-03', 'Content-Type': 'application/json'}
))
data = json.loads(resp.read())
print(json.dumps(data, indent=2))
"
```

Or replace accented keys with raw URL-encoded keys (`Dur%C3%A9e`) in jq — but Python is simpler.

## Pitfalls & Troubleshooting

### MANDATORY: Always paginate (NEVER skip)

**Every paginated endpoint (search, database query, list blocks) MUST loop through ALL pages.** Default page_size=100 covers only ~55% of the Inventaire database (180 items). Skipping pagination silently loses data.

Use Python for pagination — it avoids jq issues with accented keys:

```python
import json, urllib.request

KEY = "ntn_35...afX"  # or from vault: vault get notion/api_key
BASE = "https://api.notion.com/v1"

def paginated_query(endpoint, body=None):
    """Query with automatic pagination. Returns ALL results."""
    all_results = []
    cursor = None
    while True:
        payload = body or {}
        if cursor:
            payload["start_cursor"] = cursor
        req = urllib.request.Request(
            f"{BASE}{endpoint}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {KEY}", "Notion-Version": "2025-09-03", "Content-Type": "application/json"}
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        all_results.extend(resp.get("results", []))
        cursor = resp.get("next_cursor")
        if not cursor:
            break
    return all_results

# Example
items = paginated_query("/data_sources/{ds_id}/query", {"page_size": 100})
```

### .env file can get corrupted

Previous tool calls (read_file output with `LINE_NUM|` prefixes) can bleed into `.env`, creating lines like `334:361|NOTION_API_KEY=...`. This causes 401 errors because the key includes the garbage prefix.

If you get 401 and grep NOTION shows corrupted lines:
```bash
grep NOTION ~/.hermes/.env  # look for 361| or : prefixes
# Delete corrupted lines, then:
echo 'NOTION_API_KEY=ntn_your_key' >> ~/.hermes/.env
```

### API key fallback: check the vault

If the .env key is broken or expired, try the vault:
```bash
vault get notion/api_key
```

### jq breaks on accented property names

Notion properties like `Durée`, `Fait`, `Création`, `Possédé` cause jq syntax errors — the `//` alternative operator breaks on non-UTF8 or accented chars. Use Python instead for any query involving accented property names.

## Reading Nested Page Content: Toggles, Tables, Column Lists

Notion hides content inside parent blocks. Top-level `/blocks/{page_id}/children` only shows the first level. You MUST recurse into blocks that have `has_children: true`.

### Toggle Headings
Any heading (`heading_1/2/3`) with `is_toggleable: true` stores its content as child blocks. Query `/blocks/{heading_block_id}/children` to read them.

### Column Lists
`column_list` → `column` → content blocks. You need to go 2 levels deep:
```
page → column_list → column → heading_1 / table / paragraph etc.
```

### Tables
Tables are stored as `table` blocks → `table_row` children. Each row has `table_row.cells` = list of lists of rich text objects:
```python
for row in table_rows:
    cells = row["table_row"]["cells"]
    row_texts = []
    for cell in cells:
        txt = "".join(t["plain_text"] for t in cell)
        row_texts.append(txt)
```

### Mandatory Deep-Drill Pattern

When reading any Notion page, ALWAYS recurse into all `has_children` blocks:
```python
def read_page_recursive(page_id, depth=0):
    blocks = paginated_blocks(page_id)  # use the paginated_query pattern
    for b in blocks:
        bt = b["type"]
        if bt == "table":
            # Drill into table rows
            rows = paginated_blocks(b["id"])
            for r in rows:
                if r["type"] == "table_row":
                    cells = ["".join(t["plain_text"] for t in cell) for cell in r["table_row"]["cells"]]
                    print(f"  Row: {cells}")
        elif bt in ("column_list", "column"):
            # Drill into columns
            read_page_recursive(b["id"], depth+1)
        else:
            # Normal block with text
            txt = "".join(t["plain_text"] for t in b.get(bt, {}).get("rich_text", []))
            if txt: print(f"  [{bt}] {txt}")
        
        if b.get("has_children"):
            read_page_recursive(b["id"], depth+1)
```

**Never conclude a page is "empty" without recursing.** Content hidden in toggles/columns/tables is still content. This caused a real failure where the agent told the user a section was blank when it contained 4 detailed classification tables.

### NOTION DATABASES: Page properties must match schema exactly

If you create a page against a database (`POST /pages` with `parent: {database_id}`), every property name in `properties` must exactly match a property that exists on the database. The API returns `400: "X is not a property that exists"` if there's a mismatch — it does NOT create missing properties silently.

When creating a NEW database with custom properties, the initial `POST /databases` call sometimes **only creates the title column**. Custom properties must be added via a separate `PATCH /databases/{id}` call:

```bash
# Step 1: Create DB (only title column is guaranteed)
curl -s -X POST https://api.notion.com/v1/databases \
  -H "Authorization: Bearer $KEY" -H "Notion-Version: 2025-09-03" -H "Content-Type: application/json" \
  -d '{"parent": {"type": "page_id", "page_id": "xxx"}, "title": [{"text": {"content": "My DB"}}], "properties": {"Name": {"title": {}}}}'

# Step 2: PATCH to add custom properties
curl -s -X PATCH https://api.notion.com/v1/databases/{db_id} \
  -H "Authorization: Bearer $KEY" -H "Notion-Version: 2025-09-03" -H "Content-Type: application/json" \
  -d '{"properties": {"Status": {"select": {"options": []}}, "Notes": {"rich_text": {}}}}'

# Step 3: Verify properties exist before creating pages
curl -s https://api.notion.com/v1/databases/{db_id} | jq '.properties'
```

### NOTION PAGES WITH CHILDREN: Simpler alternative to databases

When database property creation is unreliable, create simple pages with rich children blocks instead:

```python
payload = {
    "parent": {"type": "page_id", "page_id": "xxx"},
    "properties": {"title": {"title": [{"text": {"content": "Contact - Jana"}}]}},
    "children": [
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"text": {"content": "Synthèse"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Details here"}}]}},
    ]
}
```

This avoids database schema issues entirely and works reliably.

### Rule: NEVER invent content when a block appears empty

If a block returns empty rich_text or a heading with no visible children in the API, it likely HAS children you haven't fetched yet (tables, toggles, column_lists). Always check `has_children: true` and recurse before concluding content is missing. The `drill_everywhere` pattern:

```python
def drill(block_id, indent=0):
    resp = get_children(block_id)
    for b in resp["results"]:
        bt = b["type"]
        info = b.get(bt, {})
        txt = "".join(t["plain_text"] for t in info.get("rich_text", []))
        print(f"{'  '*indent}[{bt}] {txt}")
        if b["has_children"]:
            drill(b["id"], indent + 1)
```

```bash
curl -s -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer KEY" \
  -H "Notion-Version: 2025-09-03" \
  -d '{"page_size":1}' | jq '.object'  # should be "list", not "error"
```

## Reading Nested Content: Toggles, Tables, Column Lists

**Notion hides content inside parent blocks.** A simple `GET /blocks/{page_id}/children` only returns top-level blocks. If a block has `has_children: true`, you MUST recurse into it. Missing this step results in silently inventing content that doesn't exist.

### Toggle Headings

Any heading (`heading_1/2/3`) can be toggleable (`is_toggleable: true`). Its content lives at `GET /blocks/{heading_block_id}/children`:

```python
def get_toggle_contents(toggle_block_id):
    """Get all children blocks inside a Notion toggle or toggle heading."""
    resp = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{toggle_block_id}/children",
        headers={"Authorization": f"Bearer {KEY}", "Notion-Version": "2025-09-03"}
    )).read())
    return resp["results"]
```

### Tables

Tables are blocks with type `table`. Their content is in child `table_row` blocks, where each row has a `cells` field — a list of lists of rich text:

```python
def read_table(table_block_id):
    """Read a Notion table block into a list of row-texts."""
    rows_resp = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{table_block_id}/children",
        headers={"Authorization": f"Bearer {KEY}", "Notion-Version": "2025-09-03"}
    )).read())
    table_data = []
    for row in rows_resp["results"]:
        if row["type"] == "table_row":
            cell_texts = []
            for cell in row["table_row"]["cells"]:
                txt = "".join(t["plain_text"] for t in cell)
                cell_texts.append(txt)
            table_data.append(cell_texts)
    return table_data  # [[row1_col1, row1_col2, ...], [row2_col1, ...], ...]
```

### Column Lists

`column_list` blocks contain `column` children (usually 2-4), each with `width_ratio`. Content lives inside the columns:

```
page → column_list → column → [heading_1, table, paragraph, ...]
```

### Mandatory Deep-Drill Pattern

When reading any Notion page, **ALWAYS** use recursive descent:

```python
def deep_drill(block_id, depth=0):
    """Recursively read ALL blocks including toggles, tables, columns."""
    resp = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://api.notion.com/v1/blocks/{block_id}/children",
        headers={"Authorization": f"Bearer {KEY}", "Notion-Version": "2025-09-03"}
    )).read())
    for b in resp["results"]:
        bt = b["type"]
        info = b.get(bt, {})
        txt = "".join(t["plain_text"] for t in info.get("rich_text", []))
        checked = info.get("checked", "")
        
        if bt == "table":
            # Must recurse to get table_row children
            deep_drill(b["id"], depth + 1)
        elif bt == "table_row":
            cells = info["cells"]
            texts = ["".join(t["plain_text"] for t in cell) for cell in cells]
            print(f"{'  '*depth}ROW: {texts}")
        elif bt == "column_list":
            pass  # container, recurse
        elif bt == "column":
            pass  # container, recurse
        else:
            mark = "✅" if checked is True else "⬜" if checked is False else ""
            if txt.strip():
                print(f"{'  '*depth}[{bt}] {mark} {txt}")
        
        # ALWAYS recurse if has_children
        if b["has_children"]:
            deep_drill(b["id"], depth + 1)
```

**NEVER interpret or summarize a Notion page from top-level blocks alone.** Empty `paragraph` blocks at the top level often mean the content is hidden inside a toggle or column. Drill first, then interpret.

## Embedding X/Twitter Content

**X embeds (`type: "embed"`) DO NOT WORK in Notion.** They show "error loading" because Notion's embed service can't fetch X post metadata (X blocks server-side fetching).

**What works:**
- **Bookmark blocks** → rich preview cards with title + favicon. User must click to open in X.
- **Image blocks** → `pbs.twimg.com/media/` URLs work (Notion fetches and caches images).
- **Video thumbnails** → `pbs.twimg.com/amplify_video_thumb/` URLs work as images.

**What does NOT work:**
- Embed blocks with `x.com` or `twitter.com` URLs → "error loading"
- `publish.twitter.com/oembed` URLs → same issue
- Direct video URLs from X → X blocks external access

**For inline video playback in Notion:**
- Upload to YouTube (unlisted) or Loom → embed blocks work
- Host on R2 + Cloudflare Worker → video blocks work BUT costs money
- Use bookmarks as fallback → free, requires click

**Image blocks with X URLs:**
```json
{"type": "image", "image": {"type": "external", "external": {"url": "https://pbs.twimg.com/media/XXXXX?format=jpg&name=360x360"}}}
```
Works reliably. Use `name=large` for higher resolution.

## Notes

- Page/database IDs are UUIDs (with or without dashes)
- Rate limit: ~3 requests/second average
- The API cannot set database view filters — that's UI-only
- Use `is_inline: true` when creating data sources to embed them in pages
