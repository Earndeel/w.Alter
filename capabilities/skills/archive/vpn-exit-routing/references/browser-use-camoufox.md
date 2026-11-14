# browser-use × Camoufox — validated integration (2026-08-11)

Verified end-to-end: browser-use Agent driving a real Camoufox browser with the
French exit proxy (tinyproxy 127.0.0.1:1080 → NordVPN France), navigating
OneForma, reading the login form, returning the title. First known-good recipe
for LLM-scripted interaction on top of stealth Firefox.

## Version matrix (the critical trap)

| Version | Architecture | Can it drive Camoufox? |
|---|---|---|
| 0.13.x (CLI 3.0, "Browser Harness" announced by Nous Research) | CDP-only, launches own Chromium | ❌ NO — no geckodriver/juggler backend anywhere |
| 0.6.1 / 0.5.11 | BrowserSession (pydantic model) | ❌ NO — same session model, no external browser |
| **0.4.5** | **`Browser = PatchrightBrowser \| PlaywrightBrowser`** | ✅ **YES** — accepts an external Playwright browser |

The Nous tweet ("12 browser tools → 1 browser_exec") is the 0.13.x line: great
for Chromium, forever incompatible with Firefox-based anti-detect. For stealth
interactions, pin 0.4.5.

## Known-good environment (isolated venv, NOT the Hermes venv)

```bash
python3 -m venv /root/.venv/bu-legacy
/root/.venv/bu-legacy/bin/pip install "browser-use==0.4.5" camoufox
/root/.venv/bu-legacy/bin/pip install "openai==1.85.0"   # REQUIRED pin
```

openai pinning: 0.4.5 needs `openai>=1.81.0`, but modern openai moved the
`Function` type → ImportError. 1.85.0 is the working middle ground.

## Working invocation pattern

```python
import asyncio, os
from camoufox.async_api import AsyncCamoufox
from browser_use import Agent
from browser_use.llm.openrouter.chat import ChatOpenRouter

PROXY = {"server": "http://127.0.0.1:1080"}   # tinyproxy -> NordVPN France

async def main():
    async with AsyncCamoufox(headless=True, humanize=True, geoip=False, proxy=PROXY) as browser:
        context = await browser.new_context()
        llm = ChatOpenRouter(model="deepseek/deepseek-v4-flash",
                             api_key=os.environ["OPENROUTER_API_KEY"])
        agent = Agent(task="...", browser=browser, llm=llm)   # browser= IS the Camoufox object
        history = await agent.run(max_steps=6)
```

Success signature in logs:
`🌎 Using first browser_context available in existing browser:
<Browser type=firefox executable_path=/root/.cache/ms-playwright/firefox-1522/firefox/firefox version=152.0.4-beta.28>`
(that "user-provided browser" IS Camoufox)

## Pitfalls

1. `ChatOpenRouter` does NOT read OPENROUTER_API_KEY from env — pass `api_key=`
   explicitly. Setting OPENAI_API_KEY as a copy is belt-and-suspenders, not the fix.
2. Model slugs change: `deepseek/deepseek-v4-flash:free` → 404 "unavailable for
   free, use the paid slug" (2026-08-11); use `deepseek/deepseek-v4-flash`.
3. Harmless warning: `grant_permissions: Unknown permission: clipboard-read` on
   Firefox — cosmetic, agent continues.
4. OneForma smoke result: `/center/login` loads through the combo WITHOUT
   Turnstile blocking; 8 interactive elements (email input, Continue, Google
   sign-in) readable by the agent.
5. Smoke-task source: `~/.hermes/scripts/test_browser_use_camoufox.py`.

## Placement in the Walter stack

Agreed routing (with Monsieur, 2026-08-11): walter_browse stays the ONLY facade.
browser-use × Camoufox = optional interaction-scripted backend, between
camoufox-max (passive stealth) and webtop (auth sessions/vision). Never the
default for structured extraction; never a replacement for the semantic router.

## Webtop rule (confirmed by Monsieur)

Webtop is NOT stealth or fast — it exists ONLY for (a) visual inspection via
noVNC and (b) persistent authenticated sessions. For everything else Camoufox
beats it on stealth and Scrapling on speed. Treat webtop-cdp as last resort in
the chain, not a default.