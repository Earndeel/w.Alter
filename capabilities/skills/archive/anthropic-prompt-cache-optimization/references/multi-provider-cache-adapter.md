# Multi-Provider Cache Adapter Pattern

## Problem
Hermes sends payloads to multiple providers with different caching mechanisms:
- Anthropic/Kie/MiniMax: explicit `cache_control` breakpoints on content blocks
- MiMo/DeepSeek/OpenAI: automatic prefix caching (server-side KV hash)
- Gemini: separate Context Caching API

A single payload structure must work for all, with a thin adapter layer that translates.

## Canonical payload structure (provider-agnostic)

```python
# build_system_prompt() returns a LIST of blocks, not a joined string
def build_system_prompt(agent, system_message=None):
    parts = build_system_prompt_parts(agent, system_message=system_message)
    blocks = []
    for key in ("stable", "context", "volatile"):
        if parts.get(key):
            blocks.append({"label": key, "text": parts[key]})
    return blocks
```

Order is always: stable → context → volatile. This is the universal invariant.

## Adapter: Anthropic path

```python
def prepare_for_anthropic(system_blocks, cache_ttl="5m"):
    """Convert blocks to Anthropic content format with cache_control."""
    ttl_map = {"stable": "1h", "context": "1h", "volatile": "5m"}
    return [
        {
            "type": "text",
            "text": block["text"],
            "cache_control": {
                "type": "ephemeral",
                **({"ttl": ttl_map[block["label"]]} if ttl_map[block["label"]] != "5m" else {})
            }
        }
        for block in system_blocks
    ]
```

Result: `content: [blocks]` with 3 breakpoints (uses 3 of 4 available). 4th breakpoint reserved for last user message in history.

## Adapter: MiMo/DeepSeek/OpenAI path (auto-prefix)

```python
def prepare_for_chat_completions(system_blocks):
    """Join blocks in canonical order. No cache_control. String format."""
    return "\n\n".join(block["text"] for block in system_blocks)
```

Result: `content: "SOUL...\n\nCTX...\n\nVOL..."` — a plain string.

The server's prefix hashing does the rest. Stable prefix matches across turns → cache hit on ~80% of system prompt tokens.

## Adapter: Gemini path

```python
def prepare_for_gemini(system_blocks):
    """Create a cachedContent for stable+context, pass volatile inline."""
    stable_ctx = "\n\n".join(b["text"] for b in system_blocks if b["label"] in ("stable", "context"))
    volatile = next((b["text"] for b in system_blocks if b["label"] == "volatile"), "")

    # Create cached content via Gemini API
    cache = gemini_client.cached_content.create(
        model="gemini-2.5-pro",
        contents=[{"role": "user", "parts": [{"text": stable_ctx}]}],
        ttl="3600s"
    )
    return {"cachedContent": cache.name, "inline_volatile": volatile}
```

## Decision tree in the transport layer

```python
def build_system_message(system_blocks, provider, model):
    if provider_is_anthropic_compatible(provider, model):
        content = prepare_for_anthropic(system_blocks)
    elif provider in ("xiaomi", "deepseek", "openai"):
        content = prepare_for_chat_completions(system_blocks)
    elif provider == "gemini":
        return prepare_for_gemini(system_blocks)
    else:
        # Default: safe string format
        content = prepare_for_chat_completions(system_blocks)

    return {"role": "system", "content": content}
```

## Current Hermes implementation (as of 2026-06-09)

```
agent/system_prompt.py:368-369
  build_system_prompt() → "\n\n".join(stable, context, volatile)  ← single string, structure lost

agent/conversation_loop.py:1039-1043
  api_messages = [{"role": "system", "content": effective_system}]  ← string, not blocks

agent/prompt_caching.py:49-79
  apply_anthropic_cache_control() → 1 breakpoint on system + 3 on recent messages  ← suboptimal
```

### What needs to change

1. `build_system_prompt()` returns list of blocks instead of joined string
2. `_restore_or_build_system_prompt()` caches the list (not string)
3. `apply_anthropic_cache_control()` splits system into 3 breakpoints instead of 1
4. Chat-completions transport joins blocks to string for non-Anthropic providers
5. All other code paths that read `_cached_system_prompt` must handle list vs string

### Risk: system prompt persistence

`conversation_loop.py:321-330` persists `_cached_system_prompt` to SQLite for cross-turn reuse (gateway path creates fresh AIAgent per turn). If we change from string to list, the stored format changes. Need migration or format detection on read.

## Measurement: what to expect after patching

| Metric | Before (single string) | After (3 blocks) |
|---|---|---|
| Anthropic cache hit on system | ~20% miss when volatile changes | ~5% miss (only volatile block recalculated) |
| MiMo cache hit on system | ~80% (prefix matches stable+context) | ~80% (same — ordering is what matters) |
| Breakpoints used | 4 (1 system + 3 messages) | 4 (3 system + 1 message) |
| Tokens saved per session (100 calls) | — | ~50K tokens on Anthropic, ~0 on MiMo (already optimal) |

The MiMo number shows why the ordering fix is more important than the breakpoint fix — for auto-prefix providers, the current single-string approach already works well because the stable content is at the start of the string.
