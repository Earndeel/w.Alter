# Composite model-router intelligence loop — session notes (2026-06)

## Durable lesson
The loop must not be narrowed to Design Arena ingestion. For model routing, treat Design Arena as one signal among several, with Artificial Analysis as the primary quality/cost source.

## Required source mix
1. **Artificial Analysis** — primary source for intelligence/quality, pricing, cost-to-run, and intelligence-vs-cost ratios.
2. **Pricing/endpoints in DB** — provider availability and input/output/cache prices; missing prices must be reported as a blocker, not silently defaulted.
3. **Design Arena** — specialized UX/code/design signal. Always segment by `category` and UI/view, especially `Code / Preference vs Price`.
4. **X / Reddit** — community evidence only when source URLs are captured. Do not invent Reddit consensus when search returns weak or irrelevant evidence.
5. **Internal DB history** — use existing `benchmarks`, `pricing_snapshots`, `endpoints`, and `community_evidence` tables as the consolidation layer.

## Manual-only policy
Monsieur corrected the workflow: this loop should run **only on explicit request**, not as a cron. If a previous run created a cron, remove it before proceeding.

## Pitfalls observed
- A Design-Arena-only runner produces a misleading model-router report.
- `router_scores` should stay empty rather than be populated with unreliable composite scores when key dimensions are missing.
- `Design Arena normalized_score` may be empty; use temporary per-benchmark rank normalization only in reports, and label it clearly.
- Pricing can be sparse; do not pretend cost/intelligence ratios are complete if `pricing_snapshots` is incomplete.
- `community_evidence.confidence` may be text; cast/normalize defensively when scoring.

## Recommended report shape
Return:
- sources ingested/queried;
- rows added by source;
- composite leaderboard;
- per-model AA score, Design Arena score, price/ratio status, social evidence count/confidence, availability;
- explicit gaps and next best ingestion target.

## Weighting guidance
Default composite draft should be interpretable, not magical:
- AA quality/intelligence: highest weight;
- price/intelligence ratio: high weight once pricing is complete;
- Design Arena: medium/specialized weight by category/view;
- X/Reddit evidence: small tie-breaker unless evidence quality is high;
- availability/provider coverage: practical tie-breaker.
