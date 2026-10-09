# Design Arena ingestion via hierarchical browse router (2026-06)

## What was learned

Design Arena can return `403 Forbidden` to plain Python/urllib HTTP requests while the same API endpoint is accessible through the Camoufox Max browsing tier. For model-router intelligence, do not abandon Design Arena ingestion after an HTTP 403; escalate through the browsing hierarchy and extract page text/JSON from the browser context.

Observed useful endpoint:

- `https://www.designarena.ai/api/leaderboard/judge-scores`

Successful pattern:

1. Try direct HTTP with browser-like headers for cheap path.
2. If blocked or empty, call the hierarchical browsing router with Camoufox forced for the endpoint.
3. Parse the router JSON output.
4. Extract `text` from the browser-evaluated page body.
5. Parse that text as JSON and insert benchmark rows.
6. Validate with a dry-run/global helper after ingestion.

Example command shape used in session:

```bash
python3 /root/.hermes/scripts/browse-router.py 'https://www.designarena.ai/api/leaderboard/judge-scores' --tier camoufox --text-limit 200000
python3 /tmp/ingest_designarena.py
python3 /tmp/model_router_research_run.py --dry-run
```

## Camoufox API shape used by the router

The working Camoufox Max instance exposed tab-centric endpoints:

- `POST /tab/new` with `{ "userId": "..." }`
- `POST /tab/navigate` with `{ "userId": "...", "tabId": "...", "url": "..." }`
- `POST /tab/evaluate` with `{ "userId": "...", "tabId": "...", "expression": "document.body.innerText" }`
- `POST /tab/close` with `{ "userId": "...", "tabId": "..." }`

Important pitfall: `/tab/navigate` may confirm navigation without returning useful page text. Run `/tab/evaluate` after navigation to extract `document.title`, `document.body.innerText`, and optionally `document.documentElement.outerHTML` for classification.

## Analysis caveats

When analyzing the collected data:

- Treat Artificial Analysis and Design Arena as complementary, not interchangeable.
- Design Arena may provide heterogeneous metrics per model; pivot by model and normalize per metric before ranking.
- Do not populate or trust router decisions until price, endpoint availability, and benchmark coverage are joined.
- If `router_scores` is empty, report upstream coverage/benchmarks/pricing and explicitly state that no final route decision has been computed yet.
- A pragmatic initial route score can start with quality, cost, availability, and evidence weights, but must be labeled as a proposed scoring formula until persisted and verified.
