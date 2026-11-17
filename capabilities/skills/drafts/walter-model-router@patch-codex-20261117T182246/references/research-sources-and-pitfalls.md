# walter-model-router — Research reference: every leaderboard / price source and its pitfalls (still valid).

Moved verbatim from SKILL.md on 2026-11-01.

## Research reference — sources and pitfalls (still valid)

Kept from the August collectors: how each source must be read and checked. The live readers are in
`/walter/cognition/router/research/` (AA through the Next.js data of its pages, no API key needed for the router's own sources).

### AA API v2
- `GET https://artificialanalysis.ai/api/v2/language/models/free?page=N` with `x-api-key` header. Verified 2026-11-18: the old `/api/v2/data/llms/models` returns HTTP 410.
- Read every page (`pagination.page`, `total_pages`, `has_more`), 200 models per page; reject a partial response. The existing vault key works; never expose it.
- Official current contract: https://artificialanalysis.ai/data-api/docs and https://artificialanalysis.ai/api/v2/openapi (YAML).
- Free API now publishes exact model variant slugs, headline/capability indexes and `artificial_analysis_intelligence_index_cost.cost_per_task.total_cost` (rounded to 4 decimals). The Router keeps page cost precision first; missing page costs may use that API value, with provenance. Never estimate a cost.
- Key in vault: `artificialanalysis/api_key` (NOT `artificial-analysis/api_key`, which returns 401)
- The current free endpoint does not publish all individual evaluations. Coding/Agentic indexes are retired/null. Read detailed evaluations from the full public model-page catalogue, not the chart preview.
- Source label: `aa_api_v2` (historical skill); the Router's source kind remains `aa`.

### AA cost per task
- Former method: Playwright on the Recharts "Intelligence vs Cost per Task" scatter of a model page (React fiber
  payloads of the `<circle>` elements); the router now reads the same values from the page's Next.js data
  (`intelligenceIndexCostPerTask.cost.total`, or the new API's published `cost_per_task.total_cost` when absent).
- Only 26-30 models are on one chart: for a model not on it, read ITS OWN page.
- **RÈGLE ABSOLUE: always live. Never estimate cost_per_task.**

### Kie.ai Pricing (public-page evidence first)
- For exact per-model chat rates, fetch the public family page `https://kie.ai/<family-slug>` and parse its serialized `pricingDesc`.
- Accept a `verified_rates` record only when exact input and output rates are exposed. Preserve `unverified`, `not_found`, and `fetch_error` states.
- Parse Kie’s published official-price basis and explicit top-up bonus separately from AA’s reference token prices; never store one global discount.
- The marketplace API remains useful for discovery (`POST https://api.kie.ai/client/v1/model-pricing/page`), but its catalog fields alone are not evidence for the AA/Kie discount calculation.
- If the marketplace API is blocked by Cloudflare, use Playwright `page.evaluate(fetch(...))` for discovery; the public model-page check is a separate path.

### Provider arbitration (Kie)

Kie.ai does **not** have one reliable global discount versus AA, OpenRouter, or
an official vendor price. Route to Kie only after checking the exact model page
and recording the pricing basis:

- `verified_rates`: exact Kie input/output rates are published;
- `unverified`: the page exists but does not expose exact rates;
- `not_found` / `fetch_error`: no usable evidence.

Store two separate values:

1. **Kie nominal discount vs Kie-published official pricing**, using the
   published official input/output rates and a 3:1 input/output blend.
2. **Signed Kie-vs-AA reference delta**, using AA’s own input/output prices. A
   positive delta means Kie is more expensive than AA’s reference even when Kie
   advertises a discount against a different official basis.

AA reasoning variants may use a family Kie rate only when their slug starts with
the exact published base slug (`gpt-5-6-luna-high` → `gpt-5-6-luna`). Never copy
a discount from Luna to Sol, Claude, or another provider. Keep streaming,
latency, tool-use transport, and provider availability as separate routing
criteria.

The deterministic live contract and parser evidence are maintained in
`model-benchmark-comparison/references/live-aa-kie-refresh.md`; dated percentages are
examples, not catalog truth.

### Research pitfalls (from the August collectors, still valid)

1. **Huge prices** — some models price >$10k/M: keep prices as double precision (models.offers), never a narrow NUMERIC.
2. **Model name matching between sources** — normalize: lowercase, strip all non-alnum, collapse spaces.
3. **Cost per task comes only from AA** — the router reads it from the Next.js data of an AA model page (`intelligenceIndexCostPerTask.cost.total`); never estimate it.
4. **OpenRouter pricing is $/token, not $/1M** — multiply by 1,000,000.
5. **Design Arena has two arenas** — `models` (code quality) and `agents` (agentic tasks), different categories. Full reverse-engineered API contract (endpoints, valid categories per arena, the 400 rate-limit trap, slug mapping to AA): `references/design-arena-api-contract.md`.
6. **Kie.ai pricing API blocked by Cloudflare** — use Playwright `page.evaluate(fetch(...))`, not curl.
7. **Database access** — `walter_router.store.db.connect()` (127.0.0.1:5433, ~/.pgpass); the 172.17.0.3 container address is retired.
8. **AA API v2 has TWO vault keys** — only `artificialanalysis/api_key` works. `artificial-analysis/api_key` returns 401.
9. **Codex catalogue changes** — what a ChatGPT-login Codex session serves changes (GPT-5.6 refused in August; GPT-6 / GPT-6.1 served and GPT-5.5 withdrawn on 2026-10-14): read the live catalogue (source `codex`), never a remembered list.
10. **Compare exact variant identities and index versions** — the old API/chart discrepancy was historical and must not be assumed on the current endpoint. On 2026-11-18, the new paginated free API agreed with all 141 scored variants in the full model catalogue (Router tolerance 0.05). A release slug in the new leaderboard is a family, not a variant slug; use exact catalogue identities. Keep the page/API consistency gate.
11. **Kie.ai GPT tool-use requires Responses API format** — use `function_call`/`function_call_output` items, not Chat Completions `tool_calls` messages. Call-ID prefixes, accepted tool fields, latency, and cost are route/model-specific: verify them against the exact target before routing it, and do not generalize a successful Luna probe to Astra. See `references/kie-gpt-tool-use-responses-api.md`.
12. **Next.js RSC flight prefixes change between versions** — AA's inline flight payload prefix moved from `c:` to `d:` in Aug 2026, silently emptying the old parser. Never hardcode one letter: strip any single-letter prefix (`c:`, `d:`, ...) before `json.loads`. Models arrays may also move shape; match on a stable field (`headlineValue` + `costPerTask.total`), and reject a run whose universe is suspiciously tiny instead of trusting an empty parse.
13. **A named model missing from the primary Pareto table may be below the eligibility threshold** — look up the exact live slug in the snapshot before calling it dominated, then distinguish `below_threshold` from epsilon replacement, minimum-gain pruning, or marginal-return removal. If needed, recompute a lower-threshold diagnostic into `/tmp`; never alter the primary snapshot or infer absence from a partial chart.
14. **Verified Kie token rates are not automatically a Kie cost-per-task** — report Kie input/output/cache rates and their pricing basis separately, and only publish a Kie benchmark-task estimate when the AA token mix and computed task-cost field are present; otherwise a discount percentage is not comparable to AA Cost per Task.



## AA November 2026 collection repair (verified 2026-11-18)

The current reusable reader is `research/benchmarks/aa_data.py` in the module returned by `walter path router`.
A model page carries only ~30 inline chart models. Its `initialModels` context has a public `manifest` for the full
catalogue (~742 models in the initial diagnostic; the live list changes). Exclude the separate endpoint/host
manifest. Load the same-origin `/data/*.txt` bytes; the site's own loader uses AES-GCM with the public hex key,
nonce SHA256(key)[:12], then gzip JSON (`models`). The reader authenticates, bounds sizes, requires at least 300
unique exact slugs, and keeps the previous snapshot on failure. Install the pinned dependency from the module's
`requirements-research.txt` into its own venv. Do not silently fall back to the chart preview.

Join all Next.js flight pushes before parsing JSON records: large index/evaluation records span pushes.
AA media tables renamed `API Pricing` to `Pricing` (with a numeric footnote); accept both while preserving units
and the reference-only status of media prices. Read change maps without requiring their first key to be the
Intelligence Index: its badge can expire while SciCode remains `underReview`.

Verification: 507 Router tests passed with the LLM submodule's existing FastAPI dependencies available to the test
interpreter. Reader tests covered authenticated decoding, incomplete catalogues, variant identities, split flight
records, media header changes, API pagination/failure and published costs. Live page/API: 141 compared, zero mismatch.
