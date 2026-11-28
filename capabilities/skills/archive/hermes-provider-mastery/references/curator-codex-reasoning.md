# Curator via Codex: explicit model and wire reasoning

Monsieur requires the Curator to use OpenAI Codex Luna with maximum reasoning and active consolidation. Verify the account-scoped Codex catalog before using the exact model ID; do not consult OpenRouter as authority for an OAuth-only route.

For the currently verified Curator implementation, the auxiliary binding reads provider/model/base_url/api_key and extra_body, but does not pass a standalone auxiliary reasoning_effort field to the fork. Use:

```yaml
auxiliary:
  curator:
    provider: openai-codex
    model: gpt-5.6-luna
    extra_body:
      reasoning:
        effort: max
curator:
  consolidate: true
```

Verify through `_run_llm_review` with a no-tools probe, observing only host/path/model/reasoning from the HTTP request immediately before sending. SDK extra_body merges reasoning into the actual Responses body; builder-level kwargs can still show the inherited default, so config inspection alone is insufficient. Never log authentication or raw prompts. The verified probe returned CURATOR_LUNA_OK from chatgpt.com/backend-api/codex/responses with model gpt-5.6-luna and reasoning.effort max.

Use native curator backup before real consolidation; preserve pins and unmanaged provenance boundaries. Do not silently adopt the whole library. Launch a bounded synchronous CLI run inside a durable/background process; `--background` alone returns a daemon thread that can die when the CLI exits. Report configuration success separately from verified consolidation results. The 24-hour schedule is unchanged unless Monsieur asks otherwise.
