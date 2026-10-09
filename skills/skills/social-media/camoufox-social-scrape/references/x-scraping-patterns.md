# X/Twitter Scraping Patterns

## Feed Extraction via Camoufox Snapshot

X uses virtual scrolling — only visible posts are in the DOM. Single snapshot = ~7 posts. Cumulative scraping (scroll + snapshot + merge) = ~44 posts in 25 scrolls (~90s).

### Parsing Posts from Snapshot

Posts appear as `article "..."` entries in the accessibility tree:

```
article "Author ✓ @handle Il y a X heures Texte du post... N réponses, N reposts, N J'aime, N vues"
```

Regex to extract:
```python
articles = re.findall(r'article "([^"]+)"', snapshot)
```

### Deduplication Key

Use first 80 chars (author + handle + start of text) as unique key:
```python
key = article_text[:80].strip()
```

### Engagement Metrics Parsing

```python
views = re.search(r'([\d,]+)\s*vues', text)
likes = re.search(r"([\d,.]+)\s*J['']aime", text)
reposts = re.search(r'([\d,.]+)\s*reposts', text)
replies = re.search(r'([\d,.]+)\s*réponses', text)
```

### List Navigation

1. Navigate to `https://x.com/USERNAME/lists`
2. Snapshot → find list link by name → click ref
3. Wait 6s for list feed to load
4. Start cumulative scraping

### Rate Limiting

- 2-4s random delays between scrolls (human_sim pattern)
- No detection issues with Camoufox humanize=True + residential IP
- 25 scrolls = safe limit, ~44 posts collected

## AI List Analysis Pipeline (2026-05-31 tested)

Full workflow: scrape X list → inject into Gemini → get analysis → send to Telegram.

1. Extract X cookies from Mac Brave (63 cookies)
2. Inject into Camoufox webtop (port 9378)
3. Navigate to X lists page → click target list
4. Cumulative scrape (25 scrolls, ~90s)
5. Prepare condensed prompt (~2000 chars for Gemini type API)
6. Navigate to Gemini → type prompt → Enter → wait for response
7. Parse response from accessibility tree
8. Send to Telegram (sendMessage for text, sendPhoto for screenshot)
9. Close all tabs

**Key insight**: Camoufox type API has no `append` parameter. For long prompts, prepare a condensed version instead of trying to type in chunks.
