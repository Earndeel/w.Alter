# Benchmark / Metric-Evidence Audit

Use when auditing a *benchmark closure bundle*: a deliverable (a "lot", release
artifact, or report) that asserts metric claims — pass counts, latency
percentiles, preservation counts, reduction %, equal call counts — and a
green test suite. The audit question is not "does the code work" but **"is every
reported number honest, non-vacuous, and reproducible — and does the deployment
env match the claimed baseline?"**

The workload is adversarial: default posture is that every claim may be
inflated, stale, tautological, or applied to the wrong layer. A single
doc/JSON/test incoherence fails the gate.

## 1. Reproduce the claimed numbers — do not replay the parent's claims
- Run the full suite yourself. A closure claim like "133 passed" must equal your
  live `pytest -q` result. Reproduce a failing test twice; if it fails
  deterministically, the claim is wrong *at this commit* even if it was true at
  certification time (fully-qualified commit SHA, not "latest").
- For every reported statistic, recompute where the raw data allows:
  - percentile consistency: n=30 nearest-rank → p50 = sorted[14], p95 = sorted[28]
    (index = ceil(n*p)-1). Verify the reported p50/p95 sit at those positions.
  - token==ceil(chars/4): assert at *every* reported position (min/p50/p95/max),
    not just the mean.
  - reduction % = (raw_chars - compact_chars)/raw_chars*100: recompute from the
    reported chars at each position (spot-check min/p50/p95/max).
  - equal-call-count claims: sum the per-transport dicts and confirm
    baseline==observer AND the sums equal the declared totals.
  - arm-difference p95 ≠ p95(a)-p95(b): a paired difference's p95 is the 95th of
    the per-pair differences — not subtraction of per-arm percentiles. A claim
    that reports it the naive way is wrong.

## 2. Check every gate for vacuousness / tautology
Read the *evaluation code* (the harness that mints the report), not just the
report. A gate is vacuous if it always passes by construction.
- Hardcoded invariants passed off as measured: e.g. `refs_lost=0`,
  `refs_mutated=0`, `preserved==input` where the ledger sets those fields to
  literals and defines preserved = input. That makes `input>0 and input==preserved
  and lost==mutated==0` pass with zero measuring. The *real* invariant usually
  lives elsewhere (a unit test proving the observed object is an independent
  frozen copy while the V1 caller gets the same object back). Attribute the claim
  to the layer that actually enforces it.
- A guard that is non-vacuous only if a counter exceeds zero (e.g.
  `stale_refs_checked > 0`) is good *only when that counter is genuinely positive
  in the live run*. Confirm the positive value came from real transitions (e.g.
  element-token churn across consecutive captures), not from a seeded fake.
- A "generation guard" may have no generation field at all: `generation=null`,
  `generation_bound=0`, `status=unknown_no_explicit_generation_field`. If so,
  the guard is measuring *token-set churn*, not generation identity — say so;
  don't let the name overstate it (should_fix, not must_fix, if honestly disclosed).
- A semantic-equality gate that only compares *shape* (mode/width/height/has-elements/
  has-pixels), not content, is NOT full dynamic equality. If the report honestly sets
  `dynamic_payload_is_gate=false` and proves identity via exact-return unit tests, the
  claim is sound — but flag when the closure *prose* overstates it (e.g. omits that the
  live run had 29/30 identical shapes, not 30/30).

## 3. The schema-drift-through-import-context trap (high-value, easy to miss)
A benchmark that claims "model-facing schema SHA-256 unchanged" can be *internally
consistent and still false for the live environment* if it digests the schema by
importing a pinned **release tree** instead of the deploy checkout.

Verification sequence:
1. Find what `schema_digest()`/`COMPUTER_USE_SCHEMA` resolves to: run with the
   release on `sys.path` vs the default (editable / finder-hook) environment and
   print `module.__file__`. They can differ.
2. Check `git status --short <schema.py>` in the deploy checkout — an uncommitted
   `M` is drift that the release-import digest cannot see.
3. Diff the certified release schema vs the deploy checkout schema:
   `diff release/tools/computer_use/schema.py checkout/tools/computer_use/schema.py`
   and diff their hashes. New action-enum entries (`goal`, `launch_app`, ...) whose
   descriptions the bundle itself claims to add directly contradict a "no new
   model-facing surface" / "schema unchanged" claim — must_fix.
4. The bundle's *own* architecture doc describing the new front-door action while
   the closure doc claims "schema unchanged" is an internal contradiction: the same
   change is both the deliverable and declared absent.

## 4. Sanitization / PII sweep on published artifacts
Grep every shipped `.json`/`.md` for live identifiers: numeric `pid`/`window_id`,
IPs, api keys (`sk-...`, `api_key`), MACs, emails, long base tokens. Legitimate
SHA-256 hashes (schema digests, archive checksums) will hit a 64-hex pattern —
distinguish those from live secrets. Check the sanitizer *rejects* (unit test
must fail if a sentinel like `Private`/`<secret>` escapes), not just that it runs.

## 5. Benchmark imperatives that are genuinely good (don't invent findings)
Credit these when present — they are the honest patterns to look for:
- Non-simultaneous wall-clock paired latency reported WITHOUT causal attribution
  ("this noisy non-simultaneous transport difference is reported, not attributed
  to the observer; the instrumented critical path is the causal seam").
- Unknowns reported as unknown with zero fabrication: generation
  `unknown_no_explicit_generation_field`, presence all-`unknown` with `device_calls=0`,
  a matrix refusing to backfill (L0=L1=L2=0, unknown=44, reduction 0%) because the
  historical data exposes no trustworthy route correlation, `synthetic_frequency_claim=false`.
- A non-vacuous stale-ref guard backed by a real transition and a registry unit test.
- Architecture guards proving the new code imports no device/network/LLM/persistence.

## 6. Verdict contract
Machine-validate output against the requested JSON schema. Separate:
- **must_fix**: any gate vacuous, metric invented, evidence stale at this commit,
  credential/schema leak, undisclosed benchmark bias, or doc/JSON/test incoherence
  (including a claimed pass count that the live suite contradicts, and a schema
  "unchanged" claim disproven by the deploy checkout).
- **should_fix**: honest-but-easily-overstated wording (prose omitting a disclosed
  29/30, a guard name implying a generation that isn't there, invariant-by-construction
  metrics not labeled as such).
