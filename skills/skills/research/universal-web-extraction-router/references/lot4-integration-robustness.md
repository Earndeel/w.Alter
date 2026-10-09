# Lot 4 — Integration & upgrade resilience

Implemented and validated 2026-08-11. This lot made the Walter Browse stack
well-wired, observable, and resistant to Hermes upgrades — no new browsing
features.

## 1. Tool contract exposed to the LLM (plugin schema)

`walter_browse` is presented as the general-purpose web tool. It covers:
reading a page (`content_only=true` or objective alone), searching/exploring,
structured extraction (`expected_fields`), learned capabilities
(`capability="site.tld/name"`), sessions (`session_id`), and comparison (the
agent calls it per URL). Engine internals (Scrapling, Camoufox, replay,
profiles, capabilities) are invisible to the model. `expected_fields` is now
OPTIONAL — required only for structured extraction; `content_only` triggers
the `HTML_CONTENT_DIRECT` reading path (visible text from the probe body,
zero browser).

## 2. Startup self-test & degradation

`hermes_adapter.py` (the ONLY Hermes-facing file):
- `run_startup_self_test()` — imports every component and verifies expected
  interfaces exist (feature detection, no version hardcoding; Hermes version
  recorded for diagnostics only).
- On register: logs `WALTER_BROWSE_HEALTHY` or `WALTER_BROWSE_DEGRADED
  cause=...`. Never silent, never crashes Hermes boot if the plugin API
  changed (`register_tool` kwargs are feature-detected; missing method →
  degraded log).
- Versions: `WALTER_BROWSE_VERSION=4.0.0`; schema versions — profile v4,
  session v1, capability v1 (per-entry), cache v1. Old stores load with
  missing fields defaulted (forward-compatible) and migrate on first write.

## 3. Invocation trace (observability, no secrets)

Every plugin call emits (logger):
```
WALTER_BROWSE_INVOCATION request_id=... session_id=... intent=... route=...
capability_hit=hit|miss cache_hit=hit|miss record_count=N success=True|False duration_ms=...
```
No URL, no cookie values, no payload data. Contract-tested.

## 4. walter-browse doctor

`/root/.hermes/bin/walter-browse-doctor` (also `hermes ... doctor` style via
the script): checks plugin registration contract, all component imports,
session lifecycle, capability lookup, result cache round-trip, static HTML
extraction (offline fixture), probe signature, Camoufox health (optional).
Exit 0 = healthy, 2 = degraded, 3 = hard failure.

## 5. Upgrade workflow

`/root/.hermes/scripts/check-hermes-upgrade.sh` — run after EVERY Hermes
update: audit upstream git state → doctor → Lot 4 contract tests → full
router suite → plugin import under the Hermes interpreter. Exits
`UPGRADE_CHECK_OK` or `UPGRADE_CHECK_FAILED`.

## 6. Contract & upgrade-simulation tests

`test_lot4_contracts.py` (16 tests):
- Hermes → plugin: schema shape, register callable, feature detection
  (register_tool kwargs accepted/absent), unknown handler kwargs ignored.
- Adapter → stack: component interface checks, invocation trace redaction.
- Schema versioning: store files carry versions, legacy session state loads,
  v3 profiles.json migrates to v4 preserving knowledge.
- Simulated upgrades: unknown kwargs, browser backend down (static path
  still extracts), capability DB corrupted (generic fallback), register_tool
  signature change (degrades, does not crash), old cache format ignored.

## 7. Real-harness trigger proof (instrumented)

Six prompts were run through the REAL `hermes chat` harness; tool calls were
read from the session DB (state.db `messages.tool_calls`):

| Prompt | walter_browse appelé ? | Route interne |
|---|---|---|
| "va sur books.toscrape et récupère les prix" | ✅ tool_call walter_browse | static-html / HTML_STATIC_DIRECT |
| "récupère les offres sur dummyjson" | ✅ | probe-http / HTTP_DIRECT_SUCCESS |
| "ouvre la page et explique-moi" | ✅ (après content_only contract) | static-html / HTML_CONTENT_DIRECT |
| "calcule 18 x 42" | ❌ (execute_code) | — |
| "écris un email" | ❌ (terminal) | — |
| "explique-moi HTTP" | ❌ (aucun tool) | — |

True positive 3/3, false positive 0/3. Before the Lot 4 contract fix, the
read-intent prompt fell back to `browser_navigate` after walter_browse
(because expected_fields was mandatory); after `content_only`, walter_browse
alone satisfies it.

## 8. Upstream footprint (2026-08-11)

- Hermes core modified files: 8 — ALL computer_use/plugins/web_server
  related (333 insertions), NOTHING in the agent loop, tool registry,
  toolsets, or message schema. walter_browse adds ZERO new core patches.
- Everything Walter lives outside upstream: plugins/walter-browse (adapter),
  skills/research/universal-web-extraction-router (router, sessions,
  capabilities, cache), ~/.hermes/bin (CLI + doctor), ~/.hermes/scripts
  (integration/bench scripts).

## Pitfalls & fixes discovered

1. `register()` must default `supports_register_tool_kwarg` BEFORE the import
   try-block, otherwise a failed adapter import leaves the name unbound
   (UnboundLocalError) at registration.
2. The plugin dir is `walter-browse` (dash) — importable only via
   importlib.spec_from_file_location.
3. Static-HTML reading fixture needs the full book-page structure (img alt +
   title attr + price_color); minimal `<article>` fixtures under-score the
   aggregate and yield 0 records.
4. http_probe body is reused directly (HTML_CONTENT_DIRECT, probe-http
   JSON) — no second request.
5. Signature evolution of register_tool is absorbed by feature detection +
   try/except; never version-branch on Hermes version strings.