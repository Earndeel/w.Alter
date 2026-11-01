# Voice Router Memory Integration

## Overview

The voice_router (port 12110) is the single tool exposed to Gemini Live. It routes memory lookups through the Memory Gateway ultra endpoint for <50ms recall during voice conversations.

## Architecture

```
Gemini Live → voice_router (12110) → Memory Gateway (8891) /recall/ultra
                                    ↓ (fallback)
                                    Hindsight hybrid-search (8889) /recall
```

## Changes Made (2026-05-19)

### voice_router_service.py

Added constant:
```python
MEMORY_GATEWAY_ULTRA_URL = os.getenv("VOICE_ROUTER_MEMORY_GATEWAY_ULTRA", "http://127.0.0.1:8891/recall/ultra")
```

Modified `hindsight_context_lookup()`:
1. Try Memory Gateway ultra first (2s timeout, local embedding)
2. If results found → return immediately with `source: "memory_gateway_ultra"`
3. If no results or error → fall back to Hindsight hybrid search (12s timeout)
4. Fallback response includes `source: "hindsight_fallback"`

### Response format
```json
{
  "status": "ok",
  "route": "context_lookup",
  "spoken_response": "...",
  "data": {
    "results_count": 5,
    "source": "memory_gateway_ultra",
    "latency_ms": 42
  }
}
```

## Latency Profile

| Step | Ultra (primary) | Hindsight (fallback) |
|---|---|---|
| Embedding | ~11ms (local) | ~700ms (Gemini API) |
| Qdrant search | ~30ms | ~40ms |
| Rerank | none | ~150ms (ZeRank-2) |
| Synthesis | ~400ms (Gemini) | ~400ms (Gemini) |
| **Total** | **~500ms** | **~1500ms** |

## Pitfalls

- **Browser WebSocket stale state:** After restarting voice-call server, the browser's WebSocket connection becomes stale. User MUST hard-refresh (Ctrl+Shift+R). Server-side logs show immediate connect/disconnect cycles.
- **Voice-call server restart order:** Restart voice-router BEFORE voice-call to avoid transient tool call failures.
- **Gemini Embedding API rate limiting (429):** Hitting the API too hard during backfill causes 429 errors. The fallback path (Hindsight) will also fail in this case. Local embedding (ultra) is immune to this.
