# AA Evaluations Catalog

All evaluations available on artificialanalysis.ai (May 2026). Individual leaderboard pages at `/evaluations/<slug>`.

## Agentic (real-world task completion)

| Slug | Name | Type | What it measures |
|------|------|------|-----------------|
| `gdpval-aa` | GDPval-AA | **Elo** | Agentic real-world work tasks. THE agentic benchmark. 374+ models. |
| `apex-agents-aa` | APEX-Agents-AA | Elo | Long-horizon agentic tasks |
| `tau2` | τ²-Bench Telecom | % | Tool calling accuracy (correct tool invocation with arguments) |
| `ifbench` | IFBench | % | Instruction following (multi-constraint compliance) |
| `terminalbench-hard` | Terminal-Bench Hard | % | Agentic coding in terminal environments |

### Critical: TAU2 ≠ Agentic Performance

TAU2 measures correct tool invocation. GDPval-AA measures end-to-end task completion (planning, error recovery, multi-step orchestration). They correlate poorly:

| Model | TAU2 | GDPval-AA Elo | Interpretation |
|-------|------|---------------|----------------|
| Claude Opus 4.7 (max) | 88.6% | 1753 (#3) | Poor tool calling, excellent agentic |
| Claude Sonnet 4.6 (max) | 75.7% | 1676 (#5) | Bad tool calling, great agentic |
| Grok 4.3 (high) | 97.7% (#1) | 1495 (#22) | Perfect tool calling, mediocre agentic |
| Qwen3.6 Plus | 97.7% (#1) | 1351 (#43) | Perfect tool calling, poor agentic |
| GLM-5.1 | 97.7% (#1) | 1535 (#17) | Perfect tool calling, decent agentic |

**Takeaway:** For agent model selection, use GDPval-AA Elo as the primary signal. TAU2/IFBench are secondary.

## Coding

| Slug | Name | Type | What it measures |
|------|------|------|-----------------|
| `artificial_analysis_coding_index` | Coding Index | Composite | Aggregate coding benchmark |
| `livecodebench` | LiveCodeBench | % | Real-world coding problems |
| `scicode` | SciCode | % | Scientific coding (harder, domain-specific) |

## Reasoning & Knowledge

| Slug | Name | Type | What it measures |
|------|------|------|-----------------|
| `artificial_analysis_intelligence_index` | Intelligence Index | Composite (0-100) | Main AA score across all benchmarks |
| `artificial_analysis_math_index` | Math Index | Composite | Aggregate math benchmark |
| `gpqa` | GPQA Diamond | % | Graduate-level science Q&A |
| `hle` | HLE (Humanity's Last Exam) | % | Hardest reasoning benchmark |
| `aime` | AIME | % | Competition math |
| `aime_25` | AIME 2025 | % | Recent competition math |
| `math_500` | MATH-500 | % | Standard math benchmark |
| `mmlu_pro` | MMLU-Pro | % | Knowledge & reasoning (harder MMLU) |

## Multimodal

| Slug | Name | Type | What it measures |
|------|------|------|-----------------|
| `mmmu-pro` | MMMU-Pro | % | Multimodal understanding |

## How to scrape

Individual evaluation pages return Elo or percentage rankings in a table:

```
mcp_scrapling_fetch(
  url="https://artificialanalysis.ai/evaluations/gdpval-aa",
  extraction_type="markdown",
  css_selector="table",
  wait=6000
)
```

Elo-based evaluations (GDPval-AA, APEX-Agents-AA) use confidence intervals (CI) instead of exact scores. CI format: `-X / +Y`.

Percentage-based evaluations (TAU2, IFBench, etc.) show exact percentage scores.

## API access

Individual evaluation scores are available in the v2 API response under `evaluations.<slug>`. However, the API only returns the model's own score — not the full ranked leaderboard. For rankings, scrape the website.
