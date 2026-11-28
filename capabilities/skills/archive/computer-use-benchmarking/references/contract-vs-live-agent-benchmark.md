# Contract benchmark versus live Computer Use benchmark

Use two explicitly different evidence classes.

## Contract benchmark

Purpose: validate schemas, routing contracts, safety gates, trace requirements, cost accounting, and deterministic pass/fail without touching a desktop.

Requirements:

- mark every report `mode=contract`, `evidence_class=contract_only`, and `live_execution_performed=false`;
- use fixtures and append-only event traces;
- require a non-empty route trace when a scenario declares an expected route;
- success requires both ordered route evidence and a deterministic postcondition event;
- enforce minimum as well as maximum event counts. A visual scenario with only maxima can pass with zero screenshots/vision calls — a false proof;
- count model-facing calls, backend calls, Walter Browse calls, screenshots, vision calls, warnings, focus changes, retries, tokens, and latency separately;
- never turn synthetic latency into a live performance claim.

A robust A–H suite should include native launch/observe, AX interaction, visual fallback, unknown-app observation, Web-docs-then-device execution, and active-user/no-unwarned-disruption cases. Scenario names may mention fixture apps; the generic runtime itself must contain no app recipes.

## Live benchmark

Purpose: validate the actual capture → perception → action → verification path on a controlled host.

Requirements:

- sandboxed account and reversible fixtures;
- exact target identity and fresh captures;
- emergency abort and no permission/password/payment interaction;
- real postconditions, not transport success;
- raw traces retained per independent run;
- report environmental variability and tail latency honestly.

Contract green is a prerequisite for live, never a substitute for it.

## Artifact certification

After the final code change:

1. Run the complete suite and benchmark.
2. Package code, tests, scenarios, docs, and final traces.
3. Generate a per-file `SHA256SUMS` manifest.
4. Hash the archive itself.
5. Extract into a clean directory, run `sha256sum -c`, then rerun tests and benchmark there.
6. Give an independent reviewer the exact archive and expected hash.

If the source changes afterward, regenerate the archive and re-review. Old review output certifies the old hash only.
