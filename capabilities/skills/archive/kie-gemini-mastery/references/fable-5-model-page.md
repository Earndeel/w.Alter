# Claude Fable 5 — Kie.ai Model Page Data

Source: `https://kie.ai/claude-fable-5` (SPA, scraped via Playwright innerText, 2026-07-09)

## Pricing (Kie.ai)

| | Crédits/1M | Prix Kie | Prix officiel | Réduction |
|---|---|---|---|---|
| **Input** | 800 | **$4.00** | ~$10.00 | −60% |
| **Output** | 4 000 | **$20.00** | ~$50.00 | −60% |

1 Kie credit ≈ $0.005. High-tier top-ups include +10% bonus credits → effective ~$3.60/$18.00.

## 🚫 Critical Limitation

> **« Function calling/tool use and Claude Code are not currently supported for Claude Fable 5. »**

**Router impact:** Fable 5 CANNOT be used for agentic tool-calling (the executor role). It is IDEAL as a planner/oracle — receiving context via pxpipe (PNG images of system prompt) and producing structured analysis/plans that an executor agent consumes.

## Benchmarks (from model page, vs competitors)

| Benchmark | Fable 5 | Opus 4.8 | GPT-5.5 | Gemini 3.1P |
|---|---|---|---|---|
| **SWE-Bench Pro** (agentic coding) | **80.3%** | 69.2% | 58.6% | 54.2% |
| **FrontierCode Diamond** | **29.3%** | 13.4% | 5.7% | — |
| **Terminal-Bench 2.1** | **88.0%** | 82.7% | 83.4% | 70.7% |
| **GDPval-AA** (knowledge work) | **1932** | 1890 | 1769 | 1314 |
| **GDP.pdf** (vision knowledge) | **29.8%** | 22.5% | 24.9% | 16.7% |
| **HLE no tools** | **59.0%** | 49.8% | 41.4% | 44.4% |
| **HLE with tools** | **64.5%** | 57.9% | 52.2% | 51.4% |
| **OSWorld-Verified** (computer use) | **85.0%** | 83.4% | 78.7% | 76.2% |
| **AutomationBench** (tool use) | **17.4%** | 15.5% | 12.9% | 9.6% |
| **Blueprint-Bench 2** (spatial) | **38.6%** | 14.5% | 36.2% | 26.5% |
| **Legal Agent Benchmark** | **13.3%** | 10.4% | 2.1% | 0.0% |
| **BioMysteryBench hard** | **46.1%** | 40.0% | — | — |
| **ExploitBench (Cap%)** | **78.0%** | 40.0% | 34.0% | — |
| **HealthBench Professional** | **66.0%** | 56.9% | 51.8% | — |

Fable 5 dominates EVERY category. Largest gap is Blueprint-Bench 2 (38.6% vs Opus 4.8's 14.5% — 2.7× better).

## Use Cases (from model page)

- Codebase migration projects (large-scale refactoring)
- Design-to-code review (vision + code reasoning)
- Financial/business document analysis (long reports, charts, spreadsheets)
- Legal and policy review (contracts, compliance)
- Research synthesis (papers, technical files, diagrams)
- Internal agent workflows (planning layer — NOT execution)

## Key Specs

- **Context window:** 1M tokens
- **Vision:** supports images (diagrams, charts, screenshots, PDFs)
- **Released:** June 9, 2026
- **Class:** Mythos-class (same lineage as Claude Mythos 5, but with safety guardrails)
- **Safeguards:** Requests re: cybersecurity, biology, chemistry, or distillation may trigger fallback

## pxpipe Usage

Fable 5 is the ideal pxpipe target:
- 1M context window → can ingest 100+ PNG pages
- Excellent vision reasoning (GDP.pdf 29.8% — reads charts/tables from images)
- Planning quality unmatched (HLE 59.0%, GDPval-AA 1932)
- No tool calling needed for the planner role

Architecture: `Fable 5 (pxpipe PNG → plan JSON) → Executor (tools, cheap model)`
