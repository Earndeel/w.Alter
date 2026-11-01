## Benchmarks (Oracle ARM, 7.7k active memories, measured 2026-05-22)

| Component / Path | Time | Notes |
|---|---:|---|
| PG raw recent indexed query | ~0.6ms avg | Exact/status/date lookup; fastest for audit/current rows |
| PG simple text scan | ~1.5ms avg | Fine at small scale, not semantic recall |
| Qdrant raw vector search, warm | p50 ~34ms | Vector similarity only; cold calls can spike |
| Hybrid Search `:8889` | ~479ms avg | Gemini embedding + Qdrant + ZeRank-2 rerank |
| Hindsight PG recall `:8888` | ~2265ms avg | Broad PG recall, noisier ranking |
| Hybrid vs PG recall speedup | ~4.7× | End-to-end on this deployment |

Interpretation: PG is best for exact `fact_key`/audit/current-state queries; Qdrant is best for fuzzy semantic recall and context injection. Most end-to-end latency is embedding/reranking, not Qdrant itself.

## Historical Benchmarks (Oracle ARM, 284 memories)

| Component | Time | Notes |
|---|---|---|
| Gemini Embed 2 | ~530ms | API, incompressible network cost |
| Qdrant search | ~5ms | 40x faster than PG (200ms) |
| FlashRank rerank | ~1280ms | Local CPU, highly variable on ARM |
| ZeRank-2 rerank | ~390ms | API, consistent |
| **Total (ZeRank-2)** | **~970ms** | Min 747ms |
| Write batch (6 turns) | ~15s | Qwen 3.6 Flash (OpenRouter) + Gemini embed + upsert |

## Scaling to 100k+ Memories

- Qdrant handles millions of vectors natively
- ZeRank-2 free tier: 500K bytes/min (tight at scale) — Starter $50/mo for 2M TPM
- Consider MAX_CANDIDATES=25 to keep rerank fast
- BM25 hybrid search becomes important at scale (sparse vectors in Qdrant)
- Dream cycle keeps collection clean: hard delete invalidated + dedup near-identicals
