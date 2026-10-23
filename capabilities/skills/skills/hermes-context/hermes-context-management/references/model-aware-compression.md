# Model-Aware Context Compression — Implementation Notes

## Problem

The old compression system used a flat percentage (`threshold: 0.50`) of the model's max context window. This caused two failures:

1. **Large-context models never compressed**: GPT-5.5 (1M tokens) at 50% = 500K threshold, essentially unreachable in practice. Sessions grew indefinitely.
2. **Small models compressed too early**: A 32K model at 50% = 16K, compressing before any real work happened.

## Solution: Identity-Based Absolute Thresholds

Instead of a percentage, derive the threshold from the model's identity:

- **GPT-5.5 family** → threshold = full context window (no compression)
- **All other models** → threshold = ~100K tokens, bounded by the actual window and a 64K floor

### Why 100K?

- Below 100K, most frontier models handle full context with good recall.
- Above 100K, cost and latency grow super-linearly.
- GPT-5.5 is the exception because it was explicitly designed for 1M-context coherence.

### Why disable compression for GPT-5.5?

GPT-5.5 uses "infinite context" architecture. Summarizing and discarding turns actually *hurts* performance because the model can natively attend to the full 1M tokens. Compression is pure overhead.

## Code Changes

### 1. `agent/context_compressor.py`

Add `_calculate_threshold_tokens()` and wire it into `__init__` and `update_model()`:

```python
def _calculate_threshold_tokens(self, model: str, context_length: int) -> int:
    model_lower = (model or "").lower()
    if "gpt-5.5" in model_lower or "gpt5.5" in model_lower:
        return context_length
    return max(min(100_000, context_length), MINIMUM_CONTEXT_LENGTH)
```

`update_model()` must also respect `_effective_max_threshold` — a cap set by `run_agent.py` when the auxiliary compression model has a smaller window than the main model's threshold.

### 2. `run_agent.py`

- Replace the percentage-based startup display with an absolute-token display.
- When aux-model cap triggers, store it in `_effective_max_threshold` so future model switches don't override it.

### 3. `gateway/run.py`

- Session hygiene (`_compress_token_threshold`) uses the same `_calculate_threshold_tokens` logic.
- Import `MINIMUM_CONTEXT_LENGTH` from `agent.model_metadata`.

## Testing

```python
from agent.context_compressor import ContextCompressor

# GPT-5.5 → no compression
comp = ContextCompressor("openai/gpt-5.5", quiet_mode=True)
assert comp.threshold_tokens == comp.context_length

# Claude 1M → compress at 100K
comp = ContextCompressor("anthropic/claude-sonnet-4", quiet_mode=True)
assert comp.threshold_tokens == 100_000

# GPT-4o-mini 128K → compress at 100K (bounded by window)
comp = ContextCompressor("gpt-4o-mini", quiet_mode=True)
assert comp.threshold_tokens == 100_000

# Small model below floor → floor enforced
comp = ContextCompressor("gpt-3.5-turbo", quiet_mode=True)
assert comp.threshold_tokens == 64_000  # MINIMUM_CONTEXT_LENGTH

# Aux-model cap respected after switch
comp = ContextCompressor("claude-sonnet-4", quiet_mode=True)
comp._effective_max_threshold = 80_000
comp.update_model("claude-sonnet-4", context_length=200_000)
assert comp.threshold_tokens == 80_000
```

## Extending to New Models

To add another "unlimited" model family (e.g., Gemini 3 Pro 2M):

```python
def _calculate_threshold_tokens(self, model: str, context_length: int) -> int:
    model_lower = (model or "").lower()
    if "gpt-5.5" in model_lower or "gpt5.5" in model_lower:
        return context_length
    if "gemini-3-pro" in model_lower:   # <-- add here
        return context_length
    return max(min(100_000, context_length), MINIMUM_CONTEXT_LENGTH)
```

## Related

- `hindsight-qdrant-hybrid-search` — memory system that benefits from larger uncompressed context
- `hermes-agent` — main skill for Hermes config and CLI
