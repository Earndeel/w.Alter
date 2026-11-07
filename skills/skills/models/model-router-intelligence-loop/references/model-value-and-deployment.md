# Model value, human preference, and deployment reference

## Keep evidence axes separate

Collect current source data before recommending a route. Keep Intelligence Index, Agentic Index, coding/design scores, human-preference Elo, token pricing, provider credits, and AA cost-per-task as distinct fields. A benchmark task cost is not an invoice and a subscription quota is not free API usage. Never fill unknown price or usage with zero.

Join model variants by exact base identity plus reasoning tier. A parenthesized `low`/`high`/`max` label is usually an inference setting, not a new provider model ID; verify the provider catalog before writing a picker entry. Preserve provider ownership when joining cross-provider charts.

## Frontier to recommendation

Retain the strict non-dominated frontier as the mathematical reference. Add explicit presentation layers only after it: epsilon dominance, minimum-gain/near-tie grouping, and a marginal upgrade ladder. Keep removed rows and the policy that removed them. Use matching Intelligence or Agentic task-cost axes; never mix them.

For a practical stack, choose at least a daily driver, tool-use specialist, complex-task handler, and premium fallback. Evaluate quality per successful task, latency/tail, tool reliability, context, streaming, rate limits, endpoint behavior, and provider cost—not a global leaderboard rank. Re-fetch live scores and prices before threshold-dependent decisions.

## Human-preference and community signals

Human-preference leaderboards are a separate signal from synthetic benchmarks. Join them by normalized base slug and category, preserve battle count/uncertainty, and report category/view coverage. Do not turn a missing category or unmatched slug into a negative quality claim. Community posts are evidence with source strength and recency, not a naked score; separate hands-on tests, repeated reports, and launch hype.

## Unknown or stealth models

For an unknown model, use the provider's authoritative catalog/API rather than a blocked model page. Record modalities, context, reasoning settings, supported parameters, pricing status, and creation date. Mark provider marketing claims, retention claims, free previews, and identity theories explicitly as claims or hypotheses. For identity speculation, weight architecture and behavioral signals above easily copied style; report competing hypotheses and do not assert a reveal before primary evidence.

## Open-weight deployment economics

Treat a model card as self-reported until independently tested. A repository is not an inference service. Before provisioning, preflight the actual target's architecture, VRAM/RAM, disk, GPU visibility, runtime, and network path. Compare API cost with the full rented-GPU cost, storage, setup, idle time, preemption risk, and measured throughput for the user's token mix. A quant that fits VRAM may still lack KV-cache/context headroom. Keep an open-weight derivative on a separate endpoint until tool calling, JSON adherence, repetition, context, and task success are verified.

## Reporting contract

State retrieval date, source URL, model ID, provider route, reasoning level, workload, evidence class, and unknowns. Distinguish measured, documented, derived, scenario, and unverified values. Reproduce raw runs for latency and show tails; do not present a single median as reliability. Propose router changes as reversible diffs and require approval for paid tests, new credentials, deployments, or billing changes.
