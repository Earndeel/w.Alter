# Lot 4 correction — walter_browse as the UNIQUE web front door

Applied 2026-08-11. walter_browse is the single entry point of W.Alter to
the Web — including the SIMPLEST requests. The LLM never picks between
competing web stacks; it calls walter_browse and the router picks the
lightest sufficient path.

## New: search-lite route

`search_lite.py` — Brave Search API backend (BRAVE_SEARCH_API_KEY from
`.env`; no key → DuckDuckGo HTML fallback). Returns compact results
(title/url/snippet) in ~0.6–1.3 s. ZERO LLM, ZERO browser, ZERO Scrapling.

- CLI: `universal-scraper --search "query" [--search-count N]`
- Plugin arg: `query=...` (mutually exclusive with `url`)
- Schema description rewritten: "THE default web tool ... from a quick
  search to complex browsing ... never a heavy browser when something
  lighter works".
- Web Memory checks stay zero-cost on this path: capability/domain lookup
  is not performed for generic searches (a search never fabricates a
  capability — Lot 3 principle unchanged).

## Tool exposure answer (verified in Hermes source)

`web_search`/`web_extract` are bound to the `web` toolset; Hermes only
supports `disabled_toolsets` (no per-tool disable) and walter-browse's
plugin registers under `web` too — disabling the toolset would kill the
plugin as well. Decision: keep them exposed (safe degradation if the plugin
ever fails; they are also documented as lite readers), and make walter_browse
the front door by construction:
1. schema description covers any web intent and forbids engine picking,
2. orchestrator skill says walter_browse IS the door,
3. harness battery proves simple web prompts land on walter_browse.

### 2026-08-11 update — walter-web independent toolset (verified migration)

MIGRATED: the plugin now registers with `ctx.register_tool(toolset="walter-web",
...)` — a PLUGIN toolset independent of the native `web` toolset. This was
verified compatible in Hermes source:
- `toolsets.validate_toolset()` accepts plugin toolsets via
  `_get_plugin_toolset_names()` (registry-powered).
- `_get_platform_tools()` (hermes_cli/tools_config.py) resolves toolset *names*
  per platform; its plugin block adds any plugin toolset that appears in the
  platform's `platform_toolsets` list.
- `known_plugin_toolsets` (config.yaml) pre-registers plugin toolset keys
  per platform so the config validator never warns "unknown toolset".

Config changes (config.yaml):
- `plugins.enabled` already had `walter-browse`.
- `known_plugin_toolsets: {cli: [spotify, walter-web], telegram: [spotify, walter-web]}`
- `platform_toolsets.cli` and `.telegram`: REMOVED `web` and `browser`,
  ADDED `walter-web`.

Verified at runtime (PluginManager + _get_platform_tools, HERMES_HOME=/root/.hermes):
- `walter-web` visible on cli: True → `walter_browse` resolved in LLM payload.
- `web` visible: False → `web_search`/`web_extract` NOT in LLM payload.
- `browser` visible: False → `browser_navigate` NOT in LLM payload.
- Real harness prompt "qui a gagné le GP de F1 hier ?": model called
  `tool_search → tool_describe(walter_browse) → tool_call(walter_browse,
  query=...)` then a second `walter_browse(url=formula1/races)`. No
  web_search/web_extract/browser_navigate in the session → zero bypass.

`walter-browse doctor` gained a `visible_on_current_platform` check that
asserts walter-web IS visible AND native web/browser toolsets are hidden.
(The doctor shebang was pinned to the Hermes venv python because the system
python cannot import hermes_cli.)

## Overhead measurement (2026-08-11)

- CLI direct search: 1.366 s (network-dominated)
- Same search via walter_browse plugin: 1.437 s
- Overhead ≈ 70 ms (subprocess wrapper), negligible vs ~1 s network.

## Orchestrator skill (LLM-facing, ~600 tokens)

`walter-browse-orchestrator` (walter-operating-mode): WHEN to use (any web),
WHAT the tool handles alone, WHAT the LLM provides (query/url/objective/
expected_fields/session_id only), what the LLM MUST NEVER do (no curl,
Scrapling, Camoufox, Playwright, selectors, API replay — runtime chooses),
network constraints (local default, geo per-session only), output style.
No internal implementation detail. Technical references (Lots 1–4) stay in
`references/` under the router skill, loaded only for dev/debug.

## Harness battery (real tool calls, instrumented)

Battery results (2026-08-11, sessions source=wb-frontdoor, arg-level
instrumentation):

| Prompt | walter_browse appelé | Arguments (lite path) |
|---|---|---|
| w1 "qui a gagné le GP" | ✅ | query=... (search-lite), puis url formula1 (extract) |
| w2 "météo Tokyo" | ✅ | query=... ×2 (search-lite) |
| w3 "site officiel FIA" | ✅ | query=... (search-lite) |
| w4 "ouvre et résume" | ✅ | url + content_only=true (lecture) |
| w5 "prix dummyjson" | ✅ | url + expected_fields (extraction) |
| w6 "produit iPhone" | ✅ | url search?q= + expected_fields |
| w7 "compare 3 pages" | ✅ | 2× url + expected_fields |
| n1 calcul / n2 email / n3 script / n4 HTTP / n5 résumé fourni | ❌ | aucun (FPR = 0) |

True positives 7/7, false positives 0/5. Les questions simples (w1–w3)
passent bien par search-lite (query=...), jamais un browser. Les non-Web
gardent FPR ≈ 0.

## Contract updates (test_lot4_contracts.py)

- schema: `query` param added, `required` emptied (query XOR url enforced in
  the handler), description covers universal front door.
- `test_query_search_route_is_exclusive_with_url` — search command build,
  url command build, both/neither rejected.
- `_run_router` treats `results` as usable for search payloads.
- Plugin version stays 4.0.0 (this is an integration correction, not a new
  feature; bump WALTER_BROWSE_VERSION if behavior changes again).