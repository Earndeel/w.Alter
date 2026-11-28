---
name: scrapling
description: "Scrapling backend reference for bulk/crawl operations and diagnostics; normal known-URL extraction routes through walter_browse."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [scraping, crawling, mcp, web-data, anti-bot]
    related_skills: [native-mcp, mcporter, camoufox-stealth-audit, universal-web-extraction-router, research-profile]
---

# Scrapling — Adaptive Web Scraping

Scrapling is a Python web scraping framework (43k+ stars) that covers single requests to full-scale crawls with built-in anti-bot bypass, adaptive parsing, and an MCP server for AI agents.

**Use when:**
- Running Scrapling backend diagnostics or explicit backend tests
- Extracting multiple URLs or running a crawl with bulk/spider operations
- Bypassing Cloudflare Turnstile / interstitial pages
- Building crawlers with concurrency, pause/resume, proxy rotation
- Needing an MCP-native scraping tool inside Hermes
- Doing structured data extraction with resilient CSS/XPath selectors

**Do NOT use when:**
- A single known URL needs structured extraction and `walter_browse` is available → use `walter_browse`
- Heavy social media scraping requiring real browser sessions → use `camoufox-social-scrape` or `camoufox-stealth-audit`
- Deep web app automation with user interactions → use Playwright directly or Camoufox
- Simple one-off curl calls → use `curl` or `requests`

## Role behind Walter Browse

Scrapling est un backend de la stack Walter Browse, normalement sélectionné
automatiquement pour une extraction structurée valide. Il s'insère entre :
- **Recherche** (`web_search`) → trouve les URLs quand la cible est inconnue
- **Tier 4** (Camoufox) → navigateur anti-detect pour social media / fingerprinting avancé
- **Tier 5** (Webtop) → fallback navigateur complet

### Flow d'utilisation
```
URL connue + champs structurés → walter_browse → Scrapling (si route valide)
   ↓ Bloqué ? → Camoufox (Tier 4) → CAPTCHA ? → FlareSolverr/CapSolver (Tier 6)
   ↓ Échec total ? → Webtop (Tier 5)
```

Pour le routage normal : `skill_view(name='universal-web-extraction-router')`

## Installation

See `references/installation-notes.md` for tested steps and platform-specific pitfalls.

### Option A: Virtual environment (recommended)
```bash
python3 -m venv ~/.venv/scrapling
source ~/.venv/scrapling/bin/activate
pip install "scrapling[all]"
scrapling install   # install browser deps for Dynamic/Stealthy fetchers
```

### Option B: pipx
```bash
pipx install "scrapling[all]"
scrapling install
```

### Option C: Docker
```bash
docker pull pyd4vinci/scrapling
# or
 docker pull ghcr.io/d4vinci/scrapling:latest
```

## Fetchers

Three fetcher classes. All return a `Response` object (extends `Selector`).

| Feature | `Fetcher` | `DynamicFetcher` | `StealthyFetcher` |
|---|---|---|---|
| Speed | Fastest | Medium | Medium |
| JS rendering | No | Yes | Yes |
| Anti-bot | Low | Medium | High (Cloudflare bypass) |
| Browser | None | Chromium/Chrome | Chromium/Chrome |
| Best for | Static HTML | SPA, small automation | Protected sites, enterprise targets |

### Static fetcher
```python
from scrapling.fetchers import Fetcher
page = Fetcher.get('https://example.com')
print(page.status)
```

### Stealthy fetcher (anti-bot)
```python
from scrapling.fetchers import StealthyFetcher
StealthyFetcher.adaptive = True
page = StealthyFetcher.fetch('https://example.com', headless=True, network_idle=True)
products = page.css('.product', auto_save=True)   # auto_save = store fingerprint for adaptive recovery
```

### Async fetchers
```python
from scrapling.fetchers import AsyncFetcher, AsyncStealthyFetcher, AsyncDynamicFetcher
page = await AsyncFetcher.get('https://example.com')
```

### Session-based (keep browser open)
```python
from scrapling.fetchers import StealthyFetcher
session = StealthyFetcher.session()
page1 = await session.fetch('https://example.com/login')
page2 = await session.fetch('https://example.com/dashboard')
await session.close()
```

## Parsing Engine

The `Response` / `Selector` object supports:

### CSS3 & XPath
```python
page.css('.product h2::text').get()      # first match text
page.css('.product h2::text').getall()   # all matches
page.xpath('//h1[@class="title"]').get()
page.css('a::attr(href)').getall()
```

### Text / Regex search
```python
page.find_by_text('Add to cart', partial=True)
page.find_by_regex(r'\$[\d\.]+')
```

### Similar elements
```python
product = page.find_by_text('iPhone 15')
others = product.find_similar()   # same DOM depth, tag, parent, grandparent
```

### Adaptive mode (survives redesigns)
```python
# First scrape: save element fingerprint
products = page.css('.product', auto_save=True)

# Later, if site changes:
products = page.css('.product', adaptive=True)   # auto_relocate
```

## Spiders

Scrapy-inspired async crawling with pause/resume.

```python
from scrapling.spiders import Spider, Response

class MySpider(Spider):
    name = "demo"
    start_urls = ["https://example.com/"]
    concurrent_requests = 8
    robots_txt_obey = True

    async def parse(self, response: Response):
        for item in response.css('.product'):
            yield {
                "title": item.css('h2::text').get(),
                "price": item.css('.price::text').get()
            }
        # Follow pagination
        for link in response.css('a.next::attr(href)').getall():
            yield response.follow(link, callback=self.parse)

# Run
MySpider().start()

# Pause/resume
MySpider().start(crawldir='/tmp/crawl_checkpoint')
```

### Spider features
- **Concurrent requests** via `concurrent_requests`
- **Domain filtering** via `allowed_domains`
- **Proxy rotation** via `proxy` argument or middleware
- **Blocked detection** via `is_blocked()` hook + `max_blocked_retries`
- **Checkpointing** via `crawldir` (pickle, atomic writes)
- **Response cache** for development mode
- **Output** as JSON/JSONL via `result.items.to_json()` / `to_jsonl()`

## MCP Server Integration

Scrapling provides a native MCP server with 10 tools:
- `get` / `bulk_get` — fast HTTP with browser fingerprint
- `fetch` / `bulk_fetch` — dynamic browser content
- `stealthy_fetch` / `bulk_stealthy_fetch` — anti-bot bypass
- `screenshot` — PNG/JPEG capture (returns image block, not base64)
- `open_session` / `close_session` / `list_sessions` — persistent browser sessions

### Add to Hermes config

Edit `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  scrapling:
    command: "/root/.venv/scrapling/bin/scrapling"
    args: ["mcp"]
    timeout: 120
```

Restart Hermes. Tools become available as:
- `mcp_scrapling_get`
- `mcp_scrapling_stealthy_fetch`
- `mcp_scrapling_screenshot`
- etc.

**Key advantage vs other MCP scrapers:**
Scrapling lets you pass a CSS selector to narrow content BEFORE sending it to the LLM, saving tokens and latency.

### Docker MCP server
```yaml
mcp_servers:
  scrapling:
    command: "docker"
    args: ["run", "-i", "--rm", "pyd4vinci/scrapling", "mcp"]
```

## Patterns & Snippets

### Pattern: Extract structured data
```python
from scrapling.fetchers import Fetcher
from dataclasses import dataclass

@dataclass
class Product:
    title: str
    price: str
    url: str

page = Fetcher.get('https://example.com/shop')
items = []
for el in page.css('.product'):
    items.append(Product(
        title=el.css('h2::text').get(''),
        price=el.css('.price::text').get(''),
        url=page.urljoin(el.css('a::attr(href)').get(''))
    ))
```

### Pattern: Retry with StealthyFetcher on block
```python
from scrapling.fetchers import Fetcher, StealthyFetcher

try:
    page = Fetcher.get('https://target.com')
    if page.status != 200:
        raise Exception('blocked')
except Exception:
    page = StealthyFetcher.fetch('https://target.com', headless=True)
```

### Pattern: Spider with proxy rotation
```python
from scrapling.spiders import Spider, Response

class ProxySpider(Spider):
    name = "proxy_demo"
    start_urls = ["https://target.com/page1"]
    proxy = "http://user:pass@proxy:8080"

    async def parse(self, response: Response):
        yield {"url": response.url, "status": response.status}
```

### Pattern: Batch async fetch
```python
from scrapling.fetchers import AsyncFetcher
import asyncio

urls = ["https://example.com/p/{}".format(i) for i in range(1, 11)]
pages = await AsyncFetcher.bulk_get(urls)
for p in pages:
    print(p.status, p.css('title::text').get())
```

## CLI Quick Reference

```bash
scrapling install              # install browser dependencies
scrapling mcp                  # start MCP server (stdio)
scrapling shell                # interactive scraping console
scrapling extract <url>        # quick fetch + extract
```

## Comparison with Stack

| Tool | Tier | Use case | When to pick |
|---|---|---|---|
| Scrapling | **Tier 3** | Structured scraping, crawls, anti-bot | Data extraction at scale, MCP integration, CSS/XPath parsing |
| Camoufox | Tier 4 | Stealth social media, heavy automation | X/Twitter scraping, fingerprint evasion, canvas/WebGL spoof |
| Webtop | Tier 5 | Fallback navigateur complet | Résolution manuelle, CDP direct, container Docker |
| curl/requests | — | One-off API calls | Simple HTTP, no JS |
| Playwright direct | — | Complex user flows | Multi-step forms, click chains |

**Règle de route:** Toujours essayer Scrapling (Tier 3) avant Camoufox (Tier 4) pour l'extraction structurée. Camoufox est réservé au fingerprinting avancé et au scraping social media.

## Troubleshooting

### `ModuleNotFoundError: No module named 'curl_cffi'`
Install with extras: `pip install "scrapling[all]"`

### Browser launch fails
Run `scrapling install` to download Chromium deps.

### MCP tools not appearing
- Verify path to `scrapling` binary with `which scrapling`
- Check `mcp_servers` key (not `mcp` or `servers`) in `config.yaml`
- Restart Hermes after config change

### StealthyFetcher blocked anyway
- Enable `network_idle=True`
- Use proxy rotation
- For enterprise protections (Akamai, DataDome, Kasada, Incapsula) → consider dedicated bypass APIs
