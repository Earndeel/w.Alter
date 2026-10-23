# Token/Credit Accounting Reference

## Scope

Use this reference whenever a model comparison mixes official API prices, Kie.ai prices, Artificial Analysis, or a flat-fee subscription such as ChatGPT Plus/Codex.

The governing rule is simple: **tokens are the primary unit for token-priced routes; native credits/quota are the primary unit for subscriptions; AA “task” cost is a separate benchmark measurement.**

## Evidence hierarchy

Use, in order:

1. Provider billing or response usage records with input/output/cache/reasoning tokens;
2. Provider-native credit/quota records with an attributable before/after charge;
3. Documented token-to-credit rates from the provider;
4. Explicitly named token scenarios, only for sensitivity analysis;
5. AA `Cost per Task`, only as the cost of AA's normalized benchmark workload.

A prior snapshot, a model-family discount, or a fixed `100k input + 20k output` mix is not first-party evidence of a universal per-task price.

## Canonical report fields

For every route/model/scenario, keep these fields separate:

```text
route
model_variant
reasoning_level
input_tokens
cached_input_tokens
cache_write_tokens
output_tokens
reasoning_tokens
native_unit                  # USD, credits, messages, tasks, etc.
native_charge
input_price_per_million
output_price_per_million
credits_per_input_million
credits_per_output_million
monthly_fee
fee_allocation_alpha
quota_amount
quota_window
aa_axis                      # intelligence or agentic
AA_benchmark_task_cost       # nullable; never mixed into native_charge
evidence_level               # measured, documented, scenario, unmeasured
```

Do not fill missing numeric values with zero. Use `null` plus an explicit evidence status.

## Formulas

### Token-priced API/Kie route

```text
cash_usd = input_tokens / 1e6 * input_price_per_million
         + cached_input_tokens / 1e6 * cached_input_price_per_million
         + cache_write_tokens / 1e6 * cache_write_price_per_million
         + output_tokens / 1e6 * output_price_per_million
```

Include reasoning tokens only when the provider bills them separately; otherwise do not double-count them as output.

### Credit-priced subscription

```text
credits = input_tokens / 1e6 * credits_per_input_million
        + cached_input_tokens / 1e6 * cached_credits_per_million
        + output_tokens / 1e6 * credits_per_output_million
```

If the provider does not document the rates, report native credit consumption only. Do not reverse-engineer a token conversion from an unchanged rounded counter.

### Three subscription views

```text
marginal_cash_cost = 0                         # only while included quota remains
full_economic_cost = allocated_fee / verified_quota
post_quota_cost = documented top-up or explicit fallback route
```

The full-economic view requires a verified fee, quota amount, quota window, and allocation policy. Keep `fee_allocation_alpha` explicit because the subscription may cover more than Codex.

## Exact Sol/Luna verification gate

An exact token-to-credit result for Sol or Luna is publishable only if the run contains all of the following:

1. model variant and reasoning level recorded from the provider UI/API;
2. fresh conversation or isolated request;
3. identical controlled prompt and tool policy for the compared models;
4. native credit/quota read immediately before the run;
5. provider-reported input/output/cache/reasoning tokens, when available;
6. native credit/quota read immediately after the run;
7. positive attributable delta, or a first-party usage record tying the charge to the run;
8. no hidden context, rounding, batching, or shared concurrent activity that could alter attribution.

If the UI shows only a rounded remaining balance, or the before/after value is unchanged, the correct result is:

```text
token-credit cost: unmeasured
```

Do not report `0`, do not infer the charge from AA, Kie.ai, or an illustrative token mix, and do not call a theoretical capacity “number of tasks” without naming the exact token vector.

If quota rounding prevents a single run from producing a visible delta, repeated controlled runs may be used only with explicit user authorization. Report the aggregate delta, number of runs, exact token vectors, and whether the result is an average or an exact per-run charge.

## AA separation rule

AA's `Cost per Task` is valid for comparing models on the same AA Intelligence or Agentic benchmark axis. It is not a user workload, an API invoice, or a subscription credit charge.

Reports must show separate columns/sections for:

- official API token price;
- Kie.ai token price or marketplace charge;
- observed/documented subscription credits;
- derived full-economic subscription cost;
- AA benchmark task cost.

Never replace a token-cost column with AA task cost. Never place a flat-fee route in that column as `free`.

## Minimum output wording

Use wording like:

> API/Kie cost is measured per token vector. AA cost is the normalized benchmark cost per AA task. Subscription usage is reported in native credits; any dollar equivalent is a stated allocation scenario. The Sol/Luna token-credit charge is `unmeasured` unless a first-party usage record or attributable before/after delta exists.

## Quality checks

Before finalizing a comparison:

- verify that input and output rates are not blended silently;
- verify that the model tier and reasoning level match across all sources;
- verify that every “per task” number includes its workload definition and source;
- verify that a zero marginal subscription cost is accompanied by quota consumption;
- verify that a provisional quota or price is visibly labeled;
- verify that unmeasured token-credit charges remain unmeasured rather than being filled by arithmetic from unrelated benchmarks.
