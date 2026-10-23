# Kie.ai pricing conflicts and basis separation

Use this reference when a live provider page exposes exact Kie token rates, a page-level discount claim, and an official-price basis that do not agree.

## Live evidence pattern

A refresh of `https://kie.ai/gpt-5-6` observed this pattern:

- `gpt-5-6-luna`: Kie rates approximately `$0.056` input and `$0.336` output per 1M tokens.
- Page copy: `~72% cheaper than official pricing`.
- Parsed official basis: `$1.00` input and `$6.00` output.
- Exact blended 3:1 calculation: `94.4%` below that parsed official basis.
- Independent Kie-vs-AA blended reference delta: `-72.0%`.

This is not one discount expressed three ways. It is three comparisons with potentially different bases: exact Kie versus Kie-published official, Kie page claim, and Kie versus AA reference.

A second family can show the same conflict class: `gpt-5-6-terra` exact rates calculated `77.6%` against the parsed official basis while the page claimed `72%`. `gpt-5-6-sol` calculated `72%` and matched its page claim.

## Durable rules

1. Parse exact input/output rates first. Exact rates justify `verified_rates` even if the marketing claim conflicts.
2. If an explicit official input/output basis exists, calculate the blended reduction from those rates and compare it to the page claim.
3. Mark a conflict when the absolute difference exceeds 2 percentage points; retain both values and the signed difference.
4. If no official basis exists, use `claim_only` rather than calling the page claim an exact calculation.
5. Keep Kie-vs-AA reference deltas separate from Kie's own official-price claim.
6. Apply top-up bonuses only to effective rates; a bonus does not reconcile mismatched price bases.

## Reporting

Show conflicts explicitly, for example: `94.4% calculated / 72.0% claimed ⚠️`. For claim-only rows, display `claim only`; for exact rates without an official basis, display the rates but do not invent a computed discount.
