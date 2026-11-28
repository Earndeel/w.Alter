---
name: research-profile
category: research
description: "Research worker profile for W.Alter's multi-agent architecture. Handles web research, data gathering, analysis, and synthesis."
tags: [research, profile, multi-agent, hermes]
---

# Research Profile — Hermes Research Worker

## When to Use

- Academic research, paper discovery, or literature review
- Market research, competitive analysis, or domain reconnaissance
- Data gathering from multiple sources (web, papers, APIs)
- Synthesizing findings from diverse sources into structured reports
- Any task requiring systematic information gathering and analysis

## Pitfalls

- Research quality depends on source diversity; always cross-reference
- Web scraping may hit rate limits; use caching and backoff
- Paper PDFs may require OCR for extractable text
- Market data freshness matters; check timestamps on all sources
- The research profile's auth.json must have valid credentials for its model.provider

## Purpose

Dedicated research agent spawned by W.Alter (default profile) for information gathering, analysis, and synthesis tasks.

**Architecture:**
- `default` = W.Alter (orchestrator, user-facing)
- `coder` = implementation work
- `research` = research, analysis, data gathering

## Model & Routing

**Default:** kimi-k2.6 via opencode-go (large context, strong at research/analysis)

**Smart model routing** routes each task type to the right model:
```yaml
smart_model_routing:
  enabled: true
  routes:
    - name: deep_research → deepseek-v4-pro (openrouter) — analyse, synthèse, benchmark, architecture
    - name: web_search    → mimo-v2.5-pro (xiaomi)        — cherche, trouve, prix, docs, liste
## Model

Primary: mimo-v2.5-pro via xiaomi (has credentials in auth.json)
Fallbacks: DeepSeek V4 Pro (openrouter), Gemini Flash (gemini)

**Pitfall**: The research profile's auth.json must have valid credentials for its `model.provider`. The `opencode-go` provider (kimi-k2.6) returned 401 when credentials were missing from the research profile's auth.json. Always verify credentials exist per-profile, not just in the main config.

## What Research Handles

- Web research and competitive analysis
- Technical documentation review
- Market research and pricing comparison
- API documentation exploration
- Paper/article summarization
- Data gathering from multiple sources
- Fact-checking and verification

## What Research Does NOT Handle

- Code implementation (→ coder)
- Deployment (→ coder)
- User-facing responses (→ default/W.Alter)
- Visual design (→ coder design route)

## Task Capsule Format

When W.Alter spawns research, pass only:

```
TASK TYPE: web-research
GOAL: Compare video generation APIs (Kie.ai vs Fal.ai vs PiAPI)
CONSTRAINTS:
- Focus on pricing, quality, and latency
- Include real benchmarks if available
- French output
OUTPUT: Structured comparison table + recommendation
```

## Skills Enabled

Research-focused skills only:
- arxiv, blogwatcher, polymarket
- universal-web-extraction-router, scrapling
- youtube-content
- llm-wiki, research-paper-writing
- model-benchmark-comparison
- humanizer, obsidian, google-workspace, notion, powerpoint
- ocr-and-documents, maps, himalaya

Everything else disabled to keep the profile lean.

## Tools

- web, browser, terminal, file (core research tools)
- code_execution (for data analysis)
- delegation (can spawn sub-researchers)
- memory, session_search

## Skills Enabled

Research-focused skills only:
- arxiv, blogwatcher, polymarket
- universal-web-extraction-router, scrapling
- youtube-content
- llm-wiki, research-paper-writing
- model-benchmark-comparison
- humanizer, obsidian, google-workspace, notion, powerpoint, ocr-and-documents
- maps, himalaya, hermes-agent, ideation, free-model-offer-watchdog, plan, writing-plans, spike

## Smart Model Routing

Configured routes (note: `smart_model_routing` module may not exist in current Hermes — check before relying on routing):

```yaml
smart_model_routing:
  enabled: true
  routes:
    - name: deep_research → deepseek-v4-pro (openrouter) — analyse, synthèse, benchmark, rapport
    - name: web_search → mimo-v2.5-pro (xiaomi) — cherche, trouve, prix, docs
    - name: quick → mimo-v2-flash (xiaomi) — résume, vérifie, check
```

## Verification

```bash
hermes profile show research
hermes -p research chat -Q --source tool -q "test query"
```

Check agent.log for actual model used:
```bash
tail -20 ~/.hermes/profiles/research/logs/agent.log | grep 'model='
```