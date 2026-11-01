# CRM Contact Sync — Beeper → Notion

Workflow to sync Beeper conversations into Notion contact pages.

## Prerequisites
- Beeper Desktop running on remote machine (100.127.150.1 via Tailscale)
- Notion API key with workspace access
- Vault: `vault get beeper/token` and `vault get notion/api_key`

## Step 1: Discover Beeper contacts (1-on-1 only)
```python
chats = fetch_all_chats(TOKEN)
single = [c for c in chats if c["type"] == "single" and c["title"] not in ("w.Alter", "Scena", bot_names)]
```

## Step 2: For each contact, fetch recent messages
```python
msgs = fetch_messages(chat_id, limit=10)
# Extract: last date, sender summary, text content
# Skip media/voice notes (empty text)
```

## Step 3: Create Notion pages (simple pages, NOT database entries)

Database properties in Notion API v2025-09-03 are unreliable for custom columns. Use simple pages with children blocks instead:

```python
payload = {
    "parent": {"type": "page_id", "page_id": PARENT_PAGE},
    "properties": {"title": {"title": [{"text": {"content": f"Contact - {name}"}}]}},
    "children": [
        {"object": "block", "type": "heading_1", ...},   # Synthèse
        {"object": "block", "type": "paragraph", ...},    # Réseau, date, count
        {"object": "block", "type": "heading_2", ...},    # Dernières conversations
    ] + [message_blocks]
}
```

## Pitfalls
- **Unicode names**: Beeper returns mathematical unicode (𝙎𝙖𝙧𝙪𝙣𝙮𝙖). Clean with `name.encode().decode('unicode-escape', errors='ignore')`
- **Database properties fail silently**: v2025-09-03 ignores custom properties in initial DB creation. Use simple pages.
- **Beeper timeout**: If `The read operation timed out` on fetch, skip and retry later. Not a fatal error.
- **Empty messages**: Voice notes and viewed-once messages return empty text. Handle gracefully.
- **Self-messages**: Filter out your own messages from summaries if needed.
