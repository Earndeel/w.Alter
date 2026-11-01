# Pareto Snapshot — 26 July 2026

Live data extracted from the AA Recharts scatter chart (`Intelligence vs. Cost per Task`)
on `gpt-5-5` model page. 26 models, 10 on strict frontier, 8 after pragmatic filter (min gain ≥ 0.5 pts).

## Pragmatic Frontier

| Model | Intel | Cost/task | Intel/$ | Δ Intel | Δ Cost |
|---|---|---|---|---|---|
| DeepSeek V4 Pro (max) | 44.27 | $0.0448 | 988.2 | — | — |
| GPT-5.6 Luna (max) | 51.24 | $0.2094 | 244.7 | +6.97 | +$0.16 |
| Grok 4.5 (high) | 53.83 | $0.3123 | 172.4 | +2.59 | +$0.10 |
| GPT-5.6 Sol (high) | 55.87 | $0.4530 | 123.3 | +2.04 | +$0.14 |
| GPT-5.6 Sol (xhigh) | 57.65 | $0.6825 | 84.5 | +1.78 | +$0.23 |
| GPT-5.6 Sol (max) | 58.89 | $1.0373 | 56.8 | +1.24 | +$0.35 |
| Claude Opus 5 (xhigh) | 60.07 | $1.5612 | 38.5 | +1.18 | +$0.52 |
| Claude Opus 5 (max) | 60.69 | $2.0277 | 29.9 | +0.62 | +$0.47 |

## Removed by pragmatic filter (< 0.5 pts gain)

- MiniMax-M3: intel 44.44, $0.1246 (+0.17 pts vs DeepSeek V4 Pro)
- Claude Opus 5 (medium): intel 56.28, $0.6184

## Notable non-frontier models

- Claude Fable 5 (with fallback): intel 59.86, $2.75 — strictly dominated by Claude Opus 5 (max) (higher intel + lower cost)
- GPT-5.5 (xhigh): intel 54.84, $0.99 — dominated by GPT-5.6 Sol (high) (higher intel + lower cost)
- GPT-5.5 (high): intel 53.13, $0.67 — dominated by Grok 4.5 (higher intel + lower cost)
- Claude Opus 4.8 (max): intel 55.69, $1.80 — dominated by GPT-5.6 Sol (xhigh) (higher intel + much lower cost)
- Claude Opus 4.7 (max): intel 53.53, $1.97 — dominated by Grok 4.5 (slightly higher intel, 6.3× cheaper)
- Claude Sonnet 5 (max): intel 53.35, $1.53 — dominated by GPT-5.6 Sol (medium) (similar intel, 4.9× cheaper)

## Key observations

- **DeepSeek V4 Pro** is the undisputed efficiency king: ~1000 intel/$, an order of magnitude ahead.
- **GPT-5.6 Sol family** covers the entire mid-to-premium range (high → xhigh → max), each tier adding +1.2 to +1.8 pts.
- **Grok 4.5 (high)** remains the best non-OpenAI, non-Claude premium model.
- **Claude Opus 5** holds the absolute intelligence crown (60.69) but at extreme cost.
- **Claude Fable 5** is off the frontier entirely — Opus 5 (max) strictly dominates it.
- **GPT-5.5 family** is now obsolete: GPT-5.6 Sol dominates every tier.
- **Claude Opus 4.7 and 4.8** and **Claude Sonnet 5** are dominated by cheaper models with higher intelligence.
