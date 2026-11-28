# Nitter RSS — Zero-Cost Handle Monitor Fallback

## When to use

You need the last ~20 posts from a specific X/Twitter handle and:
- `xurl` is not installed (no X API credentials)
- `x_search` is not enabled (no SuperGrok OAuth or XAI_API_KEY)
- The full `x_research_scrape.py` pipeline is overkill (no sentiment, no replies, no engagement metrics needed)
- You don't have the 30-day auth cookies exported

`nitter.net/<handle>/rss` works as of June 2026 with **no auth, no cookies, no anti-bot**. Returns ~20 most recent posts with text, timestamp, and link in ~1s. No replies, no engagement, no `from:handle` filter (may include interactions with the target).

## Status of Nitter instances (June 2026)

| Endpoint | Status | Notes |
|---|---|---|
| `nitter.net/<handle>/rss` | ✅ Works | ~1s response, ~20 items, no auth |
| `nitter.net/<handle>/status/<id>` | ❌ Empty body | JS-only page |
| `nitter.net/<handle>` (profile) | ❌ Empty body | JS-only page |
| `nitter.privacydev.net/*` | ❌ Connection refused | Dead |
| `nitter.poast.org/*` | ❌ HTTP 403 | Dead |

## Working code

```python
import urllib.request, re
from xml.etree import ElementTree as ET

url = "https://nitter.net/<HANDLE>/rss"  # e.g. NousResearch
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as r:
    xml = r.read()

root = ET.fromstring(xml)
items = root.find("channel").findall("item")

for i, item in enumerate(items, 1):
    pub = item.findtext("pubDate", "")
    link = item.findtext("link", "")
    desc = item.findtext("description", "")
    # Strip HTML and collapse whitespace
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc)).strip()
    print(f"{i}. {pub}")
    print(f"   {text[:280]}")
    print(f"   {link}")
```

## Example output (verified June 2026, @NousResearch)

```
1. Sun, 14 Jun 2026 03:50:45 GMT
   Hermes now supports this! Game changer!!!! Pavel Durov (@durov) ...
   https://nitter.net/iamlukethedev/status/2066005395248681401#m
2. Mon, 15 Jun 2026 22:40:02 GMT
   Skill docs: hermes-agent.nousresearch.co…
   https://nitter.net/NousResearch/status/2066651977874837529#m
...
```

## Important caveats

1. **Mixed sources**: The RSS for a handle includes posts the account retweets/quote-tweets, not just first-party posts. For strict `from:handle` filtering, use `x_search` or `xurl`.
2. **No replies**: RSS only surfaces top-level posts. To get the conversation thread, you need a different method.
3. **No engagement metrics**: likes/retweets/replies are stripped.
4. **Rate limit unknown**: I haven't tested burst behavior. If you hammer it, expect eventual throttling. ~1 req/sec is safe.
5. **Fragile**: Nitter is a volunteer mirror, not an X product. It can disappear at any time. Always have `x_search` as fallback.

## Decision tree

```
Need: "what did @account post recently?"
├─ xurl installed + authed? → `xurl search "from:handle" -n 20`
├─ x_search enabled? → x_search(query="from:handle", enable_image_understanding=false)
├─ Neither, but want quick text-only scan? → nitter RSS (this file)
└─ Need replies / engagement / sentiment? → full x_research_scrape.py pipeline
```

## Cron integration

For a daily veille of one handle with Telegram push:

```bash
# In a cron prompt, delegate to research profile or run inline:
python3 -c "
import urllib.request, urllib.parse
from xml.etree import ElementTree as ET
url = 'https://nitter.net/NousResearch/rss'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
root = ET.fromstring(urllib.request.urlopen(req, timeout=10).read())
items = root.find('channel').findall('item')[:5]
# Send top 5 to Telegram via bot API
token = open('/root/.hermes/.env').read().split('TELEGRAM_BOT_TOKEN=')[1].split()[0]
chat = '<CHAT_ID>'
import re
text = '\n\n'.join(
    f'• {item.findtext(\"pubDate\",\"\")[:16]}\n{re.sub(r\"\\s+\",\" \",re.sub(r\"<[^>]+>\",\"\",item.findtext(\"description\",\"\"))).strip()[:300]}'
    for item in items
)
body = f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat}&text={urllib.parse.quote(\"@NousResearch derniers posts:\n\n\"+text)}'
print(urllib.request.urlopen(body, timeout=5).read())
"
```
