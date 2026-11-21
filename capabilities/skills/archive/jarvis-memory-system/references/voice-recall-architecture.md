# Voice Recall Architecture — 3-Layer Strategy

## Problem
Gemini Live needs <50ms memory recall for fluid speech-to-speech. Gemini Embedding API takes 700-850ms (network round-trip). Unacceptable for real-time voice.

## Solution: 3 Layers

### Layer 1: Pre-load (0ms during call)
- At conversation start, Context Builder loads ~2000 tokens
- Includes: user identity, active projects, recent events, key preferences
- Gemini Live has this in system prompt — no tool call needed for 80% of questions

### Layer 2: Cache (<5ms)
- LRU cache in Memory Gateway for frequent queries
- Embeddings pre-computed, results pre-fetched
- TTL: 5 minutes
- Examples: "projets actifs", "préférences", "qui est Lucas"

### Layer 3: Local Embedding (~35ms)
- Model: all-MiniLM-L6-v2 (sentence-transformers)
- 384d vectors, 22M params, 80MB RAM
- Latency: ~11ms embedding + ~30ms Qdrant = ~35ms total
- Quality: ~80% relevance (vs ~95% for Gemini Embedding 2)
- Trade-off: 15% quality loss for 20x speed gain

## Two Separate Qdrant Collections

| Collection | Dimensions | Model | Purpose |
|---|---|---|---|
| memories | 768d | Gemini Embedding 2 | Quality recall (balanced/deep) |
| memories_local | 384d | all-MiniLM-L6-v2 | Voice recall (ultra) |

**Critical:** NEVER mix vectors from different embedding models. Cosine similarity is meaningless across embedding spaces. Each collection must use vectors from ONE model only.

## Qdrant Named Vectors API

For collections with named vectors (e.g. "dense"):

```python
# CORRECT - /points/search with named vector
{
    "vector": {"name": "dense", "vector": [0.1, 0.2, ...]},
    "limit": 5,
    "with_payload": True
}

# WRONG - this fails
{
    "query": {"dense": [0.1, 0.2, ...]},
    "limit": 5
}
```

Endpoint: `/points/search` (NOT `/points/query`)

## Voice Router Integration

The voice_router (port 12110) calls `/recall/ultra` as primary memory source:

```
voice_router → POST http://127.0.0.1:8891/recall/ultra
  → local embedding (11ms) → Qdrant memories_local (30ms) → response
  → synthesize_for_voice (Gemini API, ~400-600ms)
  → spoken_response
```

Fallback: if ultra returns 0 results, falls back to Hindsight hybrid search (8889).

## Performance (2026-05-19)

| Mode | Avg | P50 | P90 | Results |
|---|---|---|---|---|
| recall/ultra | 28ms | 36ms | 47ms | 5/query, scores 0.37-0.73 |
| recall/fast | 126ms | 139ms | 150ms | 0 (API rate-limited) |
| Local embedding | 11ms | - | - | - |
| Cache hit | 0-1ms | - | - | - |

## Backfill

```bash
# Local embeddings (384d → memories_local)
# 7,692 facts in ~136s (56/s) on CPU
python3 -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
# ... batch encode + upsert to Qdrant memories_local
"
```
