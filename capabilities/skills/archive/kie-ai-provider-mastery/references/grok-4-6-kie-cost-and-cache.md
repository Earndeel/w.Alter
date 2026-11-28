# Grok 4.6 via Kie — cost, cache, and non-substitutes

Class-level notes for making Grok 4.6 as cheap as possible **without changing the model ID**. Session evidence 2026-08-19.

## Cheapest billable path

Live Kie pricing table (`POST https://api.kie.ai/client/v1/model-pricing/page`, `modelDescription: grok-4-6`, HTTP `code=200`):

| Direction | Kie USD / 1M | xAI list (`falPrice`) | Declared discount |
|---|---:|---:|---:|
| Input | 0.80 | 2.00 | 60% |
| Cached Input | 0.20 | 0.50 | 60% |
| Output | 2.40 | 6.00 | 60% |

No Cache Writes row. Treat writes as billed at Input, not as zero. Refresh the table API before quoting these numbers in a new session.

Hermes presentation identity: named custom `providers.kie` (`model.provider: custom:kie`). Runtime rewrite: `grok-*` → `https://api.kie.ai/grok/v1` + `codex_responses`. Do not put `grok-4-6` on `kie-gpt` (`/codex/v1`).

## Cache contract (MEASURED)

Transport already sends `extra_body.prompt_cache_key` (content-addressed from session + instructions + tools) and `x-grok-conv-id`. Window ~1 h.

Kie usage shape on this route: `input_tokens` is **non-cached** prompt; `cache_read_tokens` is separate; `cache_write_tokens=0` is unknown, not proof writes are off.

Session `20260819_183448_d0cdd9` (27 calls, same host): uncached 744,886 + cache-read 1,811,456 → ~71% of prompt tokens at the $0.20 rate. Estimated input ~$0.96 vs ~$2.05 if all uncached.

Cache drops when the static prefix changes (tool schemas, skill injection, compaction rewrite of already-sent history). Frozen toolsets + no MCP on a worker profile keep the prefix stable. Do not strip useful context to chase crumbs.

Older per-call table: `references/grok-hermes-cache-investigation-20260815.md`.

## What is not free Grok 4.6

The local Grok CLI OpenAI proxy (`GET http://127.0.0.1:8766/v1/models`) listed only `grok-4.5` on 2026-08-19. That path is subscription OAuth, not the Kie Grok 4.6 catalog.

Never silently substitute `grok-4.5` / `grok-cli` when the user asked for Grok 4.6. Offer CLI 4.5 as a labeled cheaper/free **alternative**, then copy `providers.grok-cli` into the target profile if they want it selectable. Copying `providers.kie` does not copy `grok-cli`.

## Isolated profiles

Named Hermes profiles do not inherit default `providers:`. Desktop can still offer `grok-4-6` and write `provider: kie`; init then fails with `Unknown provider 'kie'` unless that profile declares the **live** slug. Copy the working session's `providers.kie` block; do not invent `kie-grok`. Leave `model.default` alone unless asked to switch the orchestrator. Procedure: `hermes-provider-routing` → `references/named-profile-custom-provider-copy.md`.
