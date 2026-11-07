# Live AA + Kie.ai refresh contract

This reference records the reusable extraction contract behind the model-value
workflow. It is intentionally separate from dated Pareto results.

## Artificial Analysis sources

Use the deterministic collector from `aa-pareto-model-optimizer` when available.
Its two live sources have different shapes:

- **Agentic Index:** `https://artificialanalysis.ai/models/capabilities/agentic`
  embeds a Next.js/RSC model array. Use `shortName`, `headlineValue`,
  `costPerTask.total`, `evalCost.total`, and the `price1m*` fields.
- **Intelligence cost-per-task:** a model page’s Recharts chart after activating
  `Intelligence vs. Cost per Task`. Read the React payload attached to SVG
  circles: `label`, `x` (USD/task), `y` (Intelligence Index), and `url`.

Join the two datasets by normalized **label and reasoning tier**. Do not join by
URL alone: AA may reuse one base URL for `high`, `xhigh`, and `max` rows.
Retain missing joins explicitly. Do not turn missing or non-positive costs into
free models.

## Kie.ai pricing evidence

Kie’s public model pages expose a serialized `pricingDesc` in the HTML. When
present, parse exact per-direction rates such as:

```text
Input ... credits (... $0.28) ... Output ... credits (... $1.68)
```

Also capture:

- the page’s published official input/output basis, when present;
- an explicit `N% cheaper` or `N% of official` claim;
- an explicitly stated top-up bonus.

A Kie rate is `verified_rates` only when exact input **and** output rates are
present. A page that says “billed per request”, “see pricing table”, or otherwise
omits an exact rate is `unverified`; do not borrow a percentage from another
model. `not_found`, `not_mapped`, and `fetch_error` stay visible in exports.

AA may publish tiered slugs such as `gpt-5-6-luna-high` while Kie publishes the
family rate at `gpt-5-6-luna`. Family inheritance is allowed only when the row
slug starts with the exact base slug plus `-`; unrelated models never receive the
rate.

Keep these two comparisons separate:

```text
Kie nominal discount vs Kie-published official basis
  = 1 - ((3 × Kie input + Kie output) / 4)
      / ((3 × official input + official output) / 4)

Kie-vs-AA reference delta
  = ((3 × Kie input + Kie output) / 4)
      / ((3 × AA input + AA output) / 4) - 1
```

A positive Kie-vs-AA delta means Kie is more expensive than AA’s reference
provider even if Kie advertises a discount against a different official basis.
Never collapse this into a single universal “Kie is X% cheaper” rule.

## Observed validation pattern

During the July 30, 2026 live refresh:

- GPT-5.6 Luna exposed Kie rates `$0.28/$1.68` versus a published `$1/$6`
  basis: 72% nominal reduction. AA’s reference was `$0.20/$1.20`, making Kie
  40% more expensive against that separate reference.
- Claude Opus 5’s public page existed but did not expose exact input/output
  rates, so its status remained `unverified`.

These values are examples of the comparison semantics, not a current catalog;
refresh before making a recommendation.

## Cron-safe execution

Use a `no_agent=True` cron job for daily collection: it avoids model calls and
reasoning-token cost. The cron wrapper in `~/.hermes/scripts/` delegates to the
skill’s `refresh.py`, writes the snapshot under
`$HERMES_HOME/cache/aa-pareto/`, and re-execs the interpreter that contains the
browser dependency when the scheduler’s worker interpreter differs.

The useful artifacts are `latest.json` and `latest.csv`; raw source captures are
for parser diagnostics only. Keep API keys out of the skill, wrapper, and output.
