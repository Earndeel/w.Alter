# Hermes Browser Use mode (browser_exec) vs the Walter browsing stack — verified 2026-08-11

## What it is

Hermes v0.20.0 ships Browser Use mode: `tools/browser_use_cli.py`. When
`browser.backend: "browser-use"` is set in config.yaml, the model receives a
single `browser_exec` tool INSTEAD of the default ~12 browser tools. It drives
browser-use CLI 3.0 (https://browser-use.com), letting the agent execute Python
freely inside the browser (Browser Harness) — click, type, inspect, adapt, in
one scripted exec instead of one tool call per click. NousResearch claims
-48% to -66% token use with no accuracy drop (tweet 2086881660658663469).

The bundled plugin `browser-browser-use` ("Browser Use cloud browser backend",
needs BROWSER_USE_API_KEY or Nous subscription) exists but is NOT enabled by
default. `hermes plugins list` shows it as `not enabled`.

## Verified facts on this system (2026-08-11, after 1095-commit update)

- `hermes --version` → v0.20.0; `tools/browser_use_cli.py` present and fully
  implemented (backend key `browser-use`, launch options, workspaces per task,
  screenshot path regex, stderr cap).
- Our config keeps `browser.engine: auto` — the 12 classic browser tools remain
  active; the mode is a config toggle away, not forced.
- Toggle mechanics confirmed by reading the source docstring: "When
  browser.backend is browser-use, the model gets browser_exec tool instead of
  default browser tools".
- Source of truth for version-dependent features: `hermes-version-check` skill
  (never assume from docs alone).

## Decision (Monsieur, 2026-08-11)

walter_browse stays the canonical facade for structured extraction. Browser Use
mode is an OPTIONAL complement for scripted interaction, NEVER a replacement:

- Do NOT flip `browser.backend: browser-use` globally — it bypasses the
  semantic extraction contract and the Walter router.
- Planned integration shape (if/when built): add browser-use as a **4th backend
  inside the Walter router** (after scrapling → camoufox-max → webtop-cdp). The
  router would generate a browser-use interaction script for pages needing
  login/multi-step/SPA hydration, execute it in subprocess, then feed the
  resulting DOM to the SAME semantic scorer — output contract unchanged for the
  model.
- Implementation notes for that backend (UPDATED after the 2026-08-11 live
  integration test + benchmark — the local path now exists):
  1. **Version trap**: `uv tool install browser-use` installs CLI 3.0 (0.13.x),
     which is **CDP-only and CANNOT drive Camoufox (Firefox)**. The verified
     local integration uses **browser-use 0.4.5** (Playwright-native era,
     `Browser = PatchrightBrowser | PlaywrightBrowser`) as a Python library in
     a DEDICATED venv (`/root/.venv/bu-legacy`, openai pinned 1.85.0), passing
     `browser=AsyncCamoufox` to `Agent(...)`. Full recipe + pitfalls:
     `agentic-web-navigation` skill → `references/browser-use-camoufox-integration.md`.
  2. Route its browser through the French proxy (tinyproxy 127.0.0.1:1080, see
     vpn-exit-routing references) — the same geo requirement as Camoufox;
     otherwise OneForma-class geo-blocks return.
  3. Escalate only when lighter backends fail the semantic contract
     (min_records / required_fields), same as webtop-cdp today.
  4. `hermes plugins list` enablement of `browser-browser-use` alone is NOT
     integration — the router wrapper is what connects it to walter_browse.
  5. **Benchmark result (2026-08-11)**: walter_browse wins hard on JSON/API
     targets (0.52 s, ~0 tokens, 5 records); browser-use×Camoufox wins on
     static HTML and interaction (reads the DOM where walter_browse's
     JSON-only scorer returns 0 records in ~45 s and escalates to
     brave-mac-cdp). The two loops are complementary — this is the empirical
     justification for the planned 4th-backend integration.

## Token rationale

The -48-66% token claim is credible and consistent with our own experience:
scripting a whole navigation in one exec call beats N round-trips of
tool-call/tool-result. The win belongs in the interaction layer, not in
structured extraction — that is exactly why the router backend shape is right.

## Cross-reference: React state introspection

For reading React/SPA internals under anti-detect (the other half of the
"comprendre tout style de page" requirement), see `camoufox-max-api-current`
skill section 5 + `references/react-fiber-hook.md` — the DevTools-hook bypass
verified on Excalidraw (509 fiber nodes) and OneForma (React 19.2.7).

## Update-survival evidence (same session)

walter-browse plugin survived a 1095-commit `hermes update` intact because it
follows the isolation pattern (see SKILL.md): plugin invokes an external CLI
(`/root/.hermes/bin/universal-scraper`) via subprocess and imports only
`hermes_constants.get_hermes_home` — no `agent/*`, `tools/*`, `cli/*` imports.
Any new backend (including browser-use) must keep that contract: subprocess
boundary + stdlib-only glue. `hermes plugins list` only shows bundled plugins;
verify custom plugins via the config plugins.enabled section and a direct
import test of `/root/.hermes/plugins/<name>/__init__.py`.