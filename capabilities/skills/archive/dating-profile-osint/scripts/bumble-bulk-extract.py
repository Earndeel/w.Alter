#!/usr/bin/env python3
"""Bulk extract all 'Your move' Bumble conversations with full context.

Usage:
  docker cp scripts/bumble-bulk-extract.py webtop:/tmp/
  docker exec webtop python3 /tmp/bumble-bulk-extract.py

Output: /tmp/bumble-conversations.json + screenshots per conversation
"""
import json, time, sys
from playwright.sync_api import sync_playwright

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://localhost:9224")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()

    # Ensure we're on the app page
    if "bumble.com/app" not in page.url:
        page.goto("https://bumble.com/app", wait_until="domcontentloaded", timeout=30000)
        time.sleep(8)

    # Step 1: Find all "Your move" conversations
    your_move = page.evaluate("""() => {
        const contacts = document.querySelectorAll('.contact');
        const results = [];
        for (const c of contacts) {
            const moveLabel = c.querySelector('.contact__move-label');
            if (!moveLabel) continue;
            const nameEl = c.querySelector('.contact__name-text');
            const msgEl = c.querySelector('.contact__message');
            results.push({
                name: nameEl?.textContent?.trim() || '',
                preview: msgEl?.textContent?.trim() || ''
            });
        }
        return results;
    }""")

    print(f"Found {len(your_move)} 'Your move' conversations")
    for ym in your_move:
        print(f"  → {ym['name']}: {ym['preview']}")

    # Step 2: Click into each and extract full context
    results = {}
    for i, ym in enumerate(your_move):
        name = ym['name']
        print(f"\n[{i+1}/{len(your_move)}] Opening {name}...")

        # Click conversation
        page.evaluate(f"""() => {{
            const contacts = document.querySelectorAll('.contact');
            for (const c of contacts) {{
                const nameEl = c.querySelector('.contact__name-text');
                if (nameEl?.textContent?.trim() === {json.dumps(name)}) {{
                    c.click();
                    return true;
                }}
            }}
            return false;
        }}""")
        time.sleep(3)

        # Extract messages
        messages = page.evaluate("""() => {
            const msgs = document.querySelectorAll('.message');
            return Array.from(msgs).map(m => ({
                direction: m.classList.contains('message--in') ? 'HER' : 'ME',
                text: m.querySelector('.message-bubble__text')?.textContent?.trim() || ''
            })).filter(m => m.text);
        }""")

        # Extract profile from right panel
        profile = page.evaluate("""() => {
            const name = document.querySelector('.profile__name')?.textContent?.trim() || '';
            const age = document.querySelector('.profile__age')?.textContent?.trim() || '';
            const bio = document.querySelector('.profile__about-text, .profile__bio, [class*="about"]')?.textContent?.trim() || '';
            const basics = document.querySelectorAll('.profile__entry, .badge, [class*="badge"]');
            const basicsText = Array.from(basics).map(b => b.textContent.trim()).filter(t => t).join(' | ');
            return {name, age, bio, basics: basicsText};
        }""")

        # Extract expiration
        expiration = page.evaluate("""() => {
            const el = document.querySelector('.messages-notice, [class*="expiration"]');
            return el?.textContent?.trim() || '';
        }""")

        # Screenshot
        page.screenshot(path=f"/tmp/bumble-{name.lower().replace(' ', '-')}.png")

        results[name] = {
            'preview': ym['preview'],
            'messages': messages[-20:],
            'profile': profile,
            'expiration': expiration
        }

        print(f"  Profile: {profile.get('name', '?')}, {profile.get('age', '?')}")
        print(f"  Bio: {profile.get('bio', '?')[:100]}")
        print(f"  Messages: {len(messages)}")
        if expiration:
            print(f"  Expiration: {expiration}")

    # Save results
    with open("/tmp/bumble-conversations.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n=== DONE: {len(results)} conversations extracted ===")
    print("Output: /tmp/bumble-conversations.json")
    print("Screenshots: /tmp/bumble-*.png")

    pw.stop()

if __name__ == "__main__":
    main()
