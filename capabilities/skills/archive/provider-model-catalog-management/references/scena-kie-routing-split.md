# Scena → Kie.ai Routing Split Recommendation

> Recommended model-to-endpoint routing for migrating Scena's 8 OpenRouter/Gemini LLM calls to Kie.ai.

## Routing Matrix

| Scena LLM Call | Kie Model | Kie Endpoint | Format | Reason |
|---|---|---|---|---|
| Agent ReAct (tools, 2K tok) | Claude (Opus 4.6-4.8) | `/claude/v1/messages` | Anthropic | Best at structured reasoning + tool chains |
| Vision (image, 300 tok) | Gemini 3.5 Flash | `/gemini-3-5-flash-openai/v1` | OpenAI | Fast + multimodal, reuse code as-is |
| Context compaction (300 tok) | Claude | `/claude/v1/messages` | Anthropic | Excellent summarization |
| Batch image prompts (1.4K) | Claude | `/claude/v1/messages` | Anthropic | Structured JSON output |
| Batch video prompts (1.6K) | Claude | `/claude/v1/messages` | Anthropic | Structured JSON output |
| Workflow JSON (4-8K, video) | Gemini 3.1 Pro | `/gemini-3.1-pro/v1` | OpenAI | Video analysis needs larger context window |
| Pipeline video analysis (5 steps) | Gemini 3.5 Flash | `/gemini-3-5-flash-openai/v1` | OpenAI | Fast, cost-effective for multi-step pipeline |
| Resize (GPT-4o → Claude) | Claude | `/claude/v1/messages` | Anthropic | Image understanding + instruction following |
| Image generation | GPT Image 2 | `/api/v1/jobs/createTask` | Task async | (unchanged) |
| Video generation | Seedance 2 | `/api/v1/jobs/createTask` | Task async | (unchanged) |

## Split Justification

- **Claude (5 calls):** Agent, compaction, batch expansions, resize. Claude dominates on structured reasoning, JSON output, and instruction following — the agent's 4000-char system prompt + tool definitions tax reasoning models heavily.
- **Gemini 3.5 Flash (3 calls):** Vision, pipeline steps, workflow JSON. Flash is fast and cheap; the OpenAI-compatible format means zero code changes for most call sites.
- **Gemini 3.1 Pro (1 call):** Workflow JSON with video (8000 tokens). Larger context + multimodal video analysis benefits from Pro's expanded capacity.

## Code Duplication Minimization

Two adapter functions cover all 8 calls:
1. `callKieOpenAILLM(env, endpoint, messages, opts)` — Gemini Flash/Pro in OpenAI format (zero conversion)
2. `callKieClaudeLLM(env, systemPrompt, messages, opts)` — Claude in Anthropic format (one-time conversion layer)

The `callGeminiAnalysis()` function (Gemini native format in `pipeline_runner.ts`) is the only non-OpenAI call — it gets replaced by `callKieOpenAILLM()` with `{type: "video_url"}` multimodal content, matching the pattern already used in `callWorkflowJsonModel()`.
