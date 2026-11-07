---
name: hierarchical-browsing-router
description: Route web access through W.Alter's browsing hierarchy instead of treating Hermes browser_* tools as the whole stack; includes escalation to Scrapling/Camoufox for protected sites.
---

# Hierarchical Browsing Router

Use when a task involves web access, protected sites, Cloudflare, JS-heavy pages, scraping, or when Monsieur asks to “recheck the browsing stack”.

## Core rule

Do **not** equate Hermes `browser_*` tools with W.Alter's full browsing stack. `browser_navigate` is a single browser tool/backend; the research stack is hierarchical and must be invoked explicitly when protection, structured extraction, or anti-detect behavior matters.

## Preferred hierarchy

1. Fast search / direct HTTP for cheap, static, public content.
2. Structured extraction layer such as Scrapling/StealthyFetcher when available.
3. Camoufox Max for JS-heavy, Cloudflare, fingerprinting, or 403/anti-bot cases.
4. Webtop/CDP or other authenticated browser fallbacks only when the earlier tiers fail or login state is required.

## Router pattern

Prefer a single wrapper/CLI that tries cheap tiers first and escalates by symptoms:

- `403`, Cloudflare page, captcha text, empty JS shell → escalate to Camoufox.
- JSON API blocked by direct HTTP → retry through Camoufox and parse rendered/body text.
- Authenticated browser state needed → use Webtop/CDP fallback rather than stateless HTTP.

Expected local wrapper, if present:

```bash
python3 /root/.hermes/scripts/browse-router.py 'https://example.com' --text-limit 1000
python3 /root/.hermes/scripts/browse-router.py 'https://protected.example/api/data' --tier camoufox --text-limit 200000
```

## Camoufox Max local API pattern

Some local Camoufox Max server variants expose tab-oriented endpoints. Minimal control flow:

```python
import requests
base = 'http://localhost:9377'
uid = 'browse-router'
tab = requests.post(base + '/tab/new', json={'userId': uid}, timeout=10).json()['tabId']
requests.post(base + '/tab/navigate', json={'userId': uid, 'tabId': tab, 'url': url}, timeout=45).raise_for_status()
text = requests.post(base + '/tab/evaluate', json={
    'userId': uid,
    'tabId': tab,
    'expression': "document.body ? document.body.innerText : ''"
}, timeout=15).json().get('result')
requests.post(base + '/tab/close', json={'userId': uid, 'tabId': tab}, timeout=10)
```

If `/tabs` or `/sessions/.../tabs` return 404, inspect the active server route names and use the `/tab/*` shape above if present.

## Verification

For every new target:

1. Test a known-simple page through the selected tier.
2. Test the target URL and capture the real status/tier/text sample.
3. If integrating into a pipeline, run the pipeline's dry-run after the scrape path succeeds.

## Pitfalls

- Saying “I tested browsing” is ambiguous. Specify whether it was Hermes `browser_*`, direct HTTP, Scrapling, Camoufox, or Webtop/CDP.
- Do not hard-code a negative conclusion after a 403 from direct HTTP. Escalate through the hierarchy first.
- Do not assume the Camoufox server API route shape from memory; check or adapt to the active server variant.

## References

- `references/designarena-camoufox-fallback.md` — Design Arena JSON endpoint fallback pattern and router notes.
