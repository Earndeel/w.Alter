# Native deterministic pruning: measurement and rollout guards

- Compare proposed thresholds to the actually enabled baseline, not to disabled pruning; the latter overstates incremental value.
- Replay chronological real-history tool rounds through native preflight and actual provider builders. Include system/developer prompts and available schemas, declare missing historical catalogs, and label chars/4 estimates separately from tokenizer counts and billed usage.
- Count prefix rewrites, same-state hot repeats, and restored-ledger no-ops. Native hysteresis means a trigger is not a hard context ceiling; a lower trigger can yield a larger final request.
- Verify every original row, argument, ID and tool pair remains recoverable in archived storage; distinguish recoverability from inline visibility. Native argument trimming and deduplication may not preserve the first messages even when oversized-tool pruning protects the head.
- Test whole-current-turn retention explicitly if needed; last-N protection does not imply current-turn protection.
- Count cached input toward context pressure. Do not lower thresholds for marginal estimated savings without semantic-quality and live-cache evidence.
- Prefer existing native mechanisms over a second projection layer, but do not deploy merely because helper tests pass. Require a meaningful incremental benefit and preservation gates.
