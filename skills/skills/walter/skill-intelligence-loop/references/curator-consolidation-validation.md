# Validate Curator consolidation without trusting its summary

- Treat a zero process exit as transport completion, not successful consolidation: inspect LLM errors and guardrail halts.
- Never infer a stalled or inactive Curator from a silent console: its review fork redirects stdout/stderr and writes its final report only at completion. Inspect timestamps and exact-session mutations in the durable ledger before asserting that it made no progress; distinguish the outer run deadline from a provider request timeout.
- After a timed-out pass, recover a separate interrupted-run receipt from the exact-session ledger and verify archive bytes against canonical pre-run snapshot paths. Preserve the native historical report; do not label a derived receipt as a successfully finalized run.
- Reconcile removals using the durable skill ledger, scoped to the exact curator session and successful archived delete mutations. Compacted `_session_messages` can omit all write calls, so absence of retained tool calls is not evidence of pruning.
- Keep retained tool-call counts separate from durable mutation counts; never synthesize tool calls into telemetry just to repair classification.
- Validate original package bytes against the pre-run backup and archive by SHA-256. Enumerate canonical tar package paths rather than blindly trusting duplicated ledger prefixes.
- Distinguish byte preservation in archives, discoverability, and semantic equivalence of new summaries. An existing archive does not prove the replacement retains all operational detail.
- Add a source-routing reference to each surviving umbrella when unique recipes remain in archives. Verify explicit `skill_view(name='.archive/<old-name>', file_path=...)` routes and preserve the archive. Old unqualified names normally stop resolving.
- After consolidation or context compaction, inspect the surviving catalogue before retrying old names. Keep the repeated-failure guard active; repair routing rather than weakening the guard.
- Check explicit cron skill bindings and textual references before declaring caller migration complete.
- Bound review work, persist evidence incrementally, and stop quota retries on HTTP 429 usage exhaustion. Do not silently substitute another provider or claim an unavailable independent review passed.
