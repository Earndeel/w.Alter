# Intelligence Index vs Agentic Index — Score Deltas

All models score lower on the Agentic Index. The gap is not uniform —
DeepSeek loses the most, Claude loses the least. This re-ranks providers.

## July 2026 Deltas

| Model | Intel Idx | Agentic Idx | Δ |
|---|---|---|---|
| DeepSeek V4 Flash (max) | 40.3 | 31.1 | −9.2 |
| DeepSeek V4 Pro (max) | 44.3 | 36.4 | −7.9 |
| GPT-5.6 Luna (xhigh) | 49.1 | 42.9 | −6.1 |
| GPT-5.6 Sol (xhigh) | 57.7 | 51.8 | −5.9 |
| GPT-5.6 Luna (max) | 51.2 | 45.6 | −5.6 |
| Claude Opus 5 (max) | 60.7 | 55.3 | −5.4 |
| GPT-5.6 Sol (max) | 58.9 | 54.0 | −4.9 |

## Impact on Rankings

- **DeepSeek drops the most**: still wins on price, but the quality gap to Luna widens
- **Luna holds up**: becomes more competitive vs DeepSeek in agentic tasks
- **Sol loses its edge**: Opus 5 dominates it more clearly on Agentic
- **Claude Opus 5**: widens its lead, clearly #1 on both indexes
- **Opus 5 (medium) at 47.1 agentic** gets dominated by Luna (max) at 45.6/$0.59 — Luna is 2.2× cheaper for −1.5 pts

## Which Index to Use

- **Agentic Index** for tool-use / agentic workloads (our primary use case)
- **Intelligence Index** for general reasoning, analysis, creative tasks
- Use both and cross-reference — the truth is in the overlap
