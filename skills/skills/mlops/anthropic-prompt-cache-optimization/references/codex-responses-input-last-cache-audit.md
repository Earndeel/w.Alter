# Codex Responses payload ordering for auto-prefix cache

Session learning: OpenAI/Codex Responses payloads can accidentally defeat automatic prefix caching when the dynamic `input` field is serialized before large stable fields such as `tools`.

## Problem pattern

Bad order:

```text
model
instructions
input        # latest user message changes every turn
tools        # large stable block after the divergence
...
```

Measured effect in Hermes on `openai-codex` / `codex_responses` with tools enabled:

```text
total_chars:                 63,581
longest_common_prefix_chars: 35,750
lcp_pct:                     56.23%
```

The first differing byte was inside `input`, so the stable tool schema block after it could not be part of the byte-prefix cache hit.

## Fix pattern

Good order:

```text
model
instructions
store
tools
tool_choice
parallel_tool_calls
prompt_cache_key
reasoning
include
timeout
extra_headers
input        # volatile conversation input last
```

Measured after moving `input` to the end:

```text
total_chars:                 63,581
longest_common_prefix_chars: 63,576
lcp_pct:                     99.9921%
instructions_chars:          35,268
tools_chars:                 27,533
input_chars:                     40
```

## Verification recipe

1. Build two equivalent API kwargs objects differing only by latest user content.
2. Serialize canonically with `json.dumps(..., separators=(",", ":"), default=str)`.
3. Compute longest common prefix length.
4. Confirm the first diff is in `"input"`, after `tools` and stable routing/cache metadata.

This is specifically for auto-prefix cache providers/paths where JSON/body order matters in practice. Do not add Anthropic `cache_control` markers to OpenAI/MiMo/DeepSeek-style routes; keep those as plain ordered payloads.
