# Router intelligence DB + dry-run notes — 2026-06

Session learnings to preserve for future W.Alter model-router work.

## Architecture correction

Monsieur corrected the workflow: do not jump straight to cronjobs. For router auto-update systems, first define the loops, shared data contracts, DB schema, and dry-run protocol, then test before recurring integration.

## Persistent store recommendation

Use the existing PostgreSQL instance, not a new server. Prefer a dedicated schema, e.g. `model_router`, so infra stays simple while tables remain isolated.

Core table groups:

- `model_router.models`: canonical model identity, aliases, provider family, modality, context/input/output limits, capability flags, release/deprecation state, confidence.
- `model_router.endpoints`: provider endpoint IDs, API base/profile, availability, region, rate limits, quotas, latency p50/p95, error rate, fallback priority.
- `model_router.pricing_snapshots`: input/output/cache/reasoning/image/video prices, batch discounts, minimum charges, free quota, promo credit, source URL, observed time.
- `model_router.benchmarks`: benchmark source/name/category, score, normalized score, methodology version, raw payload, observed time.
- `model_router.community_evidence`: qualitative community intelligence from X/Reddit; do **not** reduce it to a naive `community_score`.
- `model_router.offers`: provider/model offers, free tokens/credits, expiry, eligibility, surprise-billing risk, usable-for-tests flag.
- `model_router.internal_tests`: prompt/test version, task type, endpoint, success, quality/format scores, latency, tokens, cost, error type, raw result reference.
- `model_router.task_profiles`: task requirements and scoring weights per usage.
- `model_router.router_scores`: per-task score decomposition and explanation.
- `model_router.decisions`: selected endpoint, fallbacks, decision type, evidence snapshot, validity window, rollback target, approval/applied metadata.

## Community evidence should be qualitative

Avoid a single `community_score`; it creates false precision. Store structured qualitative evidence instead:

- `practical_feedback`
- `recurring_claims`
- `reported_strengths`
- `reported_failures`
- `provider_reliability_notes`
- `pricing_complaints`
- `migration_signals`
- `hype_level` (`low|medium|high`)
- `controversy_level` (`low|medium|high`)
- `evidence_quality` (`anecdotal|replicated|benchmarked|production`)
- `source_reputation` (`unknown|credible_user|engineer|provider|benchmarker`)
- `confidence`

Use community evidence as a modulator: `boost`, `penalty`, `warning`, or `ignore`, with a reason. It should trigger hypotheses, tests, alerts, and risk penalties; it should not decide routing alone.

## Artificial Analysis MCP pattern

AA API key may exist as `AA_API_KEY`. A useful local MCP wrapper can expose:

- status/key check;
- model search by canonical/alias;
- model detail;
- model comparison with ratios for task profiles.

In this session, a local FastMCP wrapper was created at `/root/.hermes/mcp_servers/artificial_analysis_mcp.py` and configured under `mcp_servers.artificial-analysis`. Treat this as an implementation detail to verify, not a universal path.

AA live fields observed useful for router decisions included Intelligence, Coding, HLE, GPQA, TAU2/tool-use, input/output/blended price, context, and speed.

## X/Reddit collection pitfalls

XSearch worked with simple targeted queries; overly complex boolean soup can fail or return poor results. Query strategy should decompose by model/provider/topic, e.g.:

- `<model> benchmark pricing`
- `<model> OpenRouter`
- `<model> JSON tool calling`
- `<provider> free credits trial`

Reddit exact-name searches may return nothing for emerging models. Use broadened terms, aliases, provider names, and qualitative topic terms (`pricing`, `benchmark`, `new model`, `router`, `tool calling`, `JSON`) then filter downstream. RSS/search access can work, but should be treated as one source among others.

## Dry-run: DeepSeek V4 Pro vs MiMo 2.5 Pro

Mini dry-run via OpenRouter + AA found:

- Artificial Analysis: both had same observed pricing in this session (`$0.435/M` input, `$0.87/M` output, `$0.544/M` blended). DeepSeek V4 Pro had slightly higher Intelligence/HLE; MiMo 2.5 Pro had slightly higher Coding.
- Practical test set: `extraction_json`, `coding_debug`, `router_decision`.
- DeepSeek V4 Pro completed 3/3 tests successfully with usable content.
- MiMo 2.5 Pro via OpenRouter returned `content = null` during the dry-run, so it was not valid as a production router primary on that route without further endpoint-specific debugging or native-provider testing.

Decision lesson: hosted-route behavior can override benchmark appeal. A model with excellent benchmark/cost ratio must still pass endpoint-level checks: usable content, JSON/format reliability, latency, token/cost accounting, and fallback behavior.
