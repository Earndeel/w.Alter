# Notion Export Template — X Research

## Page Structure

```python
# 1. Callout: Profile/Topic summary
{"type": "callout", "callout": {"rich_text": [rich("...")], "icon": {"type": "emoji", "emoji": "📊"}}}

# 2. Heading: Statistics
{"type": "heading_2", "heading_2": {"rich_text": [rich("📊 Statistiques")]}}

# 3. Rich paragraph: Stats (bold labels)
rich_paragraph([("Posts: ", True), ("112 • ", False), ("Auteurs: ", True), ("97", False)])

# 4. Divider + Heading per section
{"type": "divider", "divider": {}}
{"type": "heading_1", "heading_1": {"rich_text": [rich("🔧 Section Title")]}}

# 5. Code blocks: Prompts
{"type": "code", "code": {"rich_text": [rich(prompt_text)], "language": "plain text"}}

# 6. Images: External URLs from X
{"type": "image", "image": {"type": "external", "external": {"url": "https://pbs.twimg.com/media/..."}}}

# 7. Videos: Via Cloudflare Worker
{"type": "video", "video": {"type": "external", "external": {"url": "https://koda-media.lucas-jouvencon.workers.dev/file.mp4"}}}

# 8. Quotes: Original post text
{"type": "quote", "quote": {"rich_text": [rich("Original post text...")]}}

# 9. Toggles: Technical explanations
{"type": "toggle", "toggle": {"rich_text": [rich("FACS (Facial Action Coding System)")], "children": [paragraph("...")]}}

# 10. Callouts: Video captions
{"type": "callout", "callout": {"rich_text": [rich("Title — Likes")], "icon": {"type": "emoji", "emoji": "🎬"}}}
```

## Notion API Limits
- Max 100 blocks per PATCH call
- Rate limit: ~3 req/s
- Bookmark blocks work for links (rich preview)
- Embed blocks DON'T work for X URLs (error loading)
- Video blocks work for external HTTPS URLs
