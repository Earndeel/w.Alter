# x_search + Scrapling Hybrid X Research

## The Problem
x_search returns Grok's *synthesis* of X search results — no raw posts, no metadata (likes, views, dates, @handles). Pure scraping returns raw posts but X search ranks by recency, missing viral/important posts.

## The Hybrid Approach

### Step 1: x_search (find the signal)
Use x_search to find high-engagement, relevant posts. It returns status URLs.
```
hermes chat -q "x_search: 'topic' from_date=YYYY-MM-DD to_date=YYYY-MM-DD" --toolsets x_search
```
**Output**: Grok synthesis + status URLs like `https://x.com/i/status/2056867284254126577`

### Step 2: Scrapling (extract the metadata)
Use Scrapling or VPS headless Chromium to fetch each URL and extract structured data.
**NEVER use Mac Brave for this** — it hijacks the user's browser.

```python
# Via Scrapling bulk_fetch on VPS (not Mac)
urls = ["https://x.com/i/status/XXXXX", ...]
# Extract: author, text, date, likes, retweets, views, replies
```

### Step 3: Merge & Analyze
Combine x_search URLs (high signal) with scraped search results (high volume).
Dedup by text[:80]. Analyze sentiment, themes, engagement by sentiment.

## Measured Results (2026-05-20, Gemini 3.5 Flash analysis)
- Scraping alone: 92 posts, 88 authors — missed the 4 most viral posts (2588, 1073, 520, 318 likes)
- x_search alone: 13 threads + 30 replies — no metadata for quantitative analysis
- Hybrid: 134 unique posts, 100 authors, full metadata + viral posts included

## x_search Limitations
- Returns ~13 URLs per query (not 100+)
- No raw post data (likes, views, dates)
- Grok synthesizes/summarizes — can hallucinate or misattribute
- Model timeout: 60-90s is common, set `timeout_seconds: 180`
- OAuth (xai-oauth) preferred over API key — Premium+ includes SuperGrok at $0 API cost
- Multiple queries recommended for coverage (sentiment, pricing, technical, comparisons)

## X Scraping via VPS Headless Chromium
X requires login for search results. Options:
1. Use Scrapling stealthy_fetch (may work for public posts)
2. Set up persistent Chromium profile on VPS with X cookies
3. Use x_search for discovery, then fetch individual post pages for metadata
