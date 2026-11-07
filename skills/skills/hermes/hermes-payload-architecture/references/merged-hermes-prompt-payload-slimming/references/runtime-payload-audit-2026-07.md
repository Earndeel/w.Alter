# Runtime payload audit snapshot — July 2026

This is a dated worked example. Re-measure the active checkout and running service before applying thresholds.

## Evidence discipline

The successful provider body was not dumped. Payload composition was reconstructed from the persisted system prompt, runtime toolset, session working directory, and transport source. Provider token/cache totals came from successful-response telemetry; local tokenizer estimates only allocated totals across components.

## Cold payload observed

A Desktop session backed by the CLI toolset and rooted in the Hermes repository measured:

- provider first-call input: 38,541 tokens;
- reconstructed fixed payload: about 40,739 tokens;
- system prompt: about 27,123 tokens;
- repository instruction context: about 15,161 tokens;
- skills catalog: about 7,362 tokens;
- 36 tool schemas: about 13,616 tokens.

Repository context was roughly 37% of the cold fixed payload. Keep it for repository engineering; use a neutral workspace for general concierge sessions.

## Dynamic growth and cache

Over twelve calls, provider input grew from 38,541 to 168,592 tokens. Cumulative input was 1,380,435 tokens, including 1,206,784 cache-read tokens. Warm calls reached 94–97% cache reuse.

Conclusion: cache reuse was healthy. The cost and latency issue was the size of cached history, particularly consumed tool outputs, not systematic cache invalidation.

A prompt-view simulation found about 96,507 tokens of raw tool results. Structured digests for consumed oversized outputs reduced the simulated tool layer to about 6,729 tokens while leaving the canonical ledger intact. Treat this as an upper-bound case study and validate quality plus tool-call pairing before rollout.

## Call-count multiplier

A snapshot of 30 recent Desktop sessions contained 1,103 provider calls for 114 user messages, about 9.68 calls per user message. Input volume was 5,319,730 uncached tokens plus 112,220,928 cache-read tokens.

Eliminate redundant agent loops before micro-editing prompt prose: one avoided late call removes one full accumulated payload.

## Compression behavior observed

For `gpt-5.6-sol` on Codex Responses:

- resolved context length: 272,000 tokens;
- reserved output: 32,000 tokens;
- effective input budget: 240,000 tokens;
- effective threshold: 85%;
- compression threshold: 204,000 tokens.

The raw percentage setting did not describe runtime behavior because the Codex auto-raise path raised the effective threshold. The absolute token-cap setting limits that effective threshold. The proactive-pruning setting independently enables deterministic old-tool-result pruning and was disabled in the observed configuration.

For cost-sensitive long sessions, test an absolute cap near 100,000 tokens and proactive pruning around 70,000–80,000 tokens. These are starting points, not universal defaults.

## Diagnostic mismatch

The nominal Desktop prompt-size path reported three tools while the running Desktop gateway resolved the CLI toolset and exposed 36. Measure with the live session's platform resolution, enabled toolsets, model, and working directory; a nominal profile report is not proof of the live payload.

## Durable conclusions

1. Preserve the raw ledger and slim only the provider-bound prompt view.
2. Digest consumed large tool outputs while preserving protocol pairs and recall references.
3. Use neutral workspaces outside repository engineering sessions.
4. Record per-call layer metrics and delta since the prior call.
5. Prefer stable per-session tool profiles over turn-by-turn schema mutation.
6. Optimize dominant measured layers before memory or persona micro-edits.
7. Do not rewrite persisted message content as the routine token-saving strategy.
