#!/usr/bin/env python3
"""X Research — Fast scraper pipeline (target: <3 min)
Usage: python3 x_research_scrape.py "topic" [--mode recherche|veille] [--max-posts 70] [--threads 10]
"""
import sys, os, json, time, re, random
sys.path.insert(0, os.path.dirname(__file__))

from x_research_db import create_search, finish_search, bulk_insert, insert_snapshot, get_analysis
from x_research_analyze import enrich_post, compute_stats, format_report
from playwright.sync_api import sync_playwright

COOKIES_PATH = "/tmp/x_cookies.json"

def load_cookies():
    with open(COOKIES_PATH) as f: return json.load(f)

def inject_cookies(context, cookies):
    pw_cookies = []
    for c in cookies:
        cookie = {"name": c["name"], "value": c["value"], "domain": c["domain"],
                  "path": c.get("path", "/"), "secure": c.get("secure", True),
                  "httpOnly": c.get("httpOnly", False)}
        if c.get("sameSite") and c["sameSite"] in ["Strict", "Lax", "None"]:
            cookie["sameSite"] = c["sameSite"]
        pw_cookies.append(cookie)
    context.add_cookies(pw_cookies)

def extract_posts(page):
    return page.evaluate(r"""() => {
        const articles = document.querySelectorAll('article[data-testid="tweet"]');
        const results = [];
        for (const art of articles) {
            try {
                let user = '', url = '';
                for (const el of art.querySelectorAll('a[role="link"]')) {
                    const href = el.getAttribute('href');
                    if (href && href.match(/^\/[a-zA-Z0-9_]+\/status\/\d+$/)) { url = 'https://x.com' + href; user = href.split('/')[1]; }
                    if (!user && href && href.match(/^\/[a-zA-Z0-9_]+$/) && href.length > 2) user = href.replace('/', '');
                }
                const text = art.querySelector('[data-testid="tweetText"]')?.innerText || '';
                const date = art.querySelector('time')?.getAttribute('datetime') || '';
                const getNum = (el) => {
                    if (!el) return 0;
                    const m = (el.getAttribute('aria-label')||'').match(/([\d,\.]+[KkMm]?)/);
                    if (!m) return 0;
                    let n = m[1].replace(/,/g,'');
                    if (n.match(/[Kk]$/)) return Math.round(parseFloat(n)*1000);
                    if (n.match(/[Mm]$/)) return Math.round(parseFloat(n)*1000000);
                    return parseInt(n)||0;
                };
                results.push({author:'@'+user, text:text.trim(), date, url,
                    likes:getNum(art.querySelector('[data-testid="like"]')),
                    retweets:getNum(art.querySelector('[data-testid="retweet"]')),
                    replies:getNum(art.querySelector('[data-testid="reply"]')),
                    views:getNum(art.querySelector('a[href*="/analytics"]'))});
            } catch(e) {}
        }
        return results;
    }""")

def scroll_and_collect(page, max_scrolls=5):
    all_posts, seen = [], set()
    for _ in range(max_scrolls):
        posts = extract_posts(page)
        for p in posts:
            key = p['text'][:80]
            if key and key not in seen: seen.add(key); all_posts.append(p)
        page.evaluate("window.scrollBy(0, 2000)")
        time.sleep(random.uniform(2.0, 3.5))
    return all_posts

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("topic")
    parser.add_argument("--mode", default="recherche", choices=["recherche", "veille"])
    parser.add_argument("--max-posts", type=int, default=70)
    parser.add_argument("--threads", type=int, default=10)
    args = parser.parse_args()

    topic, mode, max_posts, max_threads = args.topic, args.mode, args.max_posts, args.threads
    queries = [f'"{topic}"', f'"{topic}" lang:en', f'"{topic}" -filter:replies',
               f'"{topic}" (review OR opinion OR benchmark)', f'"{topic}" (price OR cost)',
               f'"{topic}" (coding OR agentic)', f'"{topic}" (Claude OR GPT)', f'"{topic}" (fast OR speed)']
    search_id = create_search(topic, mode, queries)
    print(f"[{search_id}] Recherche: {topic} (mode={mode})", flush=True)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    cookies = load_cookies()
    all_posts, seen = [], set()

    # Phase 1: X search f=top + f=live
    print(f"\n{'='*50}\nPhase 1: X search (top + live)", flush=True)
    for qi, (q, sort) in enumerate([(f'"{topic}"','top'), (f'"{topic}" lang:en','top'),
                                     (f'"{topic}" min_faves:5','top'), (f'"{topic}"','live')]):
        if len(all_posts) >= max_posts: break
        ctx = browser.new_context(); inject_cookies(ctx, cookies)
        page = ctx.new_page()
        print(f"  [{qi+1}] {q} ({sort})", end="", flush=True)
        try:
            page.goto(f"https://x.com/search?q={q}&src=typed_query&f={sort}", wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(3, 5))
            posts = scroll_and_collect(page, max_scrolls=4)
            new = 0
            for p in posts:
                key = p['text'][:80]
                if key and key not in seen: seen.add(key); p['source']=f'x_{sort}'; p['query']=q; all_posts.append(p); new += 1
            print(f" → {new} new ({len(all_posts)} total)", flush=True)
        except Exception as e: print(f" → ERROR: {str(e)[:60]}", flush=True)
        ctx.close(); time.sleep(random.uniform(1.5, 3))

    # Phase 2: Google site:x.com
    print(f"\n{'='*50}\nPhase 2: Google site:x.com", flush=True)
    for qi, q in enumerate([f'site:x.com "{topic}"', f'site:x.com "{topic}" review OR opinion']):
        ctx = browser.new_context(); page = ctx.new_page()
        print(f"  [{qi+1}] {q}", end="", flush=True)
        try:
            page.goto(f"https://www.google.com/search?q={q}&num=15", wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2, 3))
            urls = page.evaluate(r"""() => { return [...new Set([...document.querySelectorAll('a[href*="x.com"]')].map(a=>a.href).filter(h=>h.match(/x\.com\/.*\/status\/\d+/)))]; }""")
            print(f" → {len(urls)} URLs", end="", flush=True)
            new = 0
            for xurl in urls[:8]:
                try:
                    ctx2 = browser.new_context(); inject_cookies(ctx2, cookies)
                    p2 = ctx2.new_page()
                    p2.goto(xurl, wait_until="domcontentloaded", timeout=12000)
                    time.sleep(random.uniform(2, 3))
                    posts = extract_posts(p2)
                    for p in posts:
                        key = p['text'][:80]
                        if key and key not in seen: seen.add(key); p['source']='google'; p['query']=q; all_posts.append(p); new += 1
                    ctx2.close()
                except: pass
                time.sleep(random.uniform(2, 4))
            print(f" → {new} new ({len(all_posts)} total)", flush=True)
        except Exception as e: print(f" → ERROR: {str(e)[:60]}", flush=True)
        ctx.close(); time.sleep(random.uniform(2, 4))

    # Phase 3: Top threads
    print(f"\n{'='*50}\nPhase 3: Top threads", flush=True)
    sorted_posts = sorted(all_posts, key=lambda p: p.get('likes', 0), reverse=True)
    thread_urls = [p['url'] for p in sorted_posts if p.get('url')][:max_threads]
    thread_count = 0
    for i, turl in enumerate(thread_urls):
        ctx = browser.new_context(); inject_cookies(ctx, cookies)
        page = ctx.new_page()
        print(f"  [{i+1}] {turl.split('/')[-1]}", end="", flush=True)
        try:
            page.goto(turl, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2.5, 4))
            replies = extract_posts(page); new = 0
            for j, p in enumerate(replies):
                key = p['text'][:80]
                if key and key not in seen: seen.add(key); p['source']='thread'; all_posts.append(p); new += 1
            if replies: thread_count += 1
            print(f" → {new} replies ({len(all_posts)} total)", flush=True)
        except Exception as e: print(f" → ERROR: {str(e)[:60]}", flush=True)
        ctx.close(); time.sleep(random.uniform(2, 4))

    # Phase 4: Analyze + Store
    print(f"\n{'='*50}\nPhase 4: Analyze + Store", flush=True)
    for p in all_posts: enrich_post(p)
    stats = compute_stats(all_posts)
    inserted = bulk_insert(search_id, all_posts, source="scraping")
    print(f"  Inserted {inserted} new posts into PG", flush=True)
    insert_snapshot(search_id, stats)
    finish_search(search_id, len(all_posts), thread_count)
    analysis = get_analysis(search_id)
    report = format_report(topic, search_id, analysis)
    print(f"\n{report}", flush=True)
    browser.close(); pw.stop()
    print(f"\nDone in search_id={search_id}", flush=True)

if __name__ == "__main__":
    main()
