---
name: react-agent-prompting
description: ReAct (Reasoning & Acting) pattern for LLM agents — force internal_thought JSON before every action, enable autonomous tool chaining with observation loops.
version: 1.0.0
tags: [agent, react, tool-calling, prompt-engineering, multi-step]
---

# ReAct Agent Prompting

Force an LLM agent to THINK before ACTING, then OBSERVE results and RE-THINK — creating an autonomous reasoning loop.

## Core Pattern

### 1. internal_thought (Mandatory Pre-Action Block)

Before every response or tool call, the agent must generate a JSON reasoning block:

```json
{
  "internal_thought": {
    "analyse": "What the user actually wants",
    "variables_manquantes": ["style", "format", "duration"],
    "risques": ["what could go wrong"],
    "plan": ["step 1", "step 2", "step N"],
    "prochaine_action": "consultation | appel_outil_X | validation_client"
  }
}
```

Rules:
- `analyse`: Reformulate the request precisely. If vague, say so.
- `variables_manquantes`: List what's missing. If empty, the agent can act.
- `risques`: Anticipate failures.
- `plan`: Steps to the final deliverable.
- `prochaine_action`: Exactly what happens next.

### 2. Tool Chaining Loop

The agent can chain tools autonomously without asking the user:

```
generate_image(prompt="...") 
  → observe: image generated but wrong ratio
  → internal_thought: "Wrong ratio, need to recrop"
  → resize_image(aspect_ratio="9:16")
  → observe: image recropped
  → internal_thought: "Image OK, present to user"
  → response: "Here's the result, is this right?"
```

**Safety limit: max 4 chained tool calls.** Beyond that, inform the user and ask for help.

### 3. Error Recovery Chain

If a tool fails:
1. internal_thought: analyze the error
2. Try a fallback (e.g., provider A fails → try provider B)
3. If format issue → use correction tool (resize, re-encode)
4. After 2 correction attempts → inform user

## Implementation Notes

- The internal_thought is INVISIBLE to the end user — it stays in reasoning context
- When the agent speaks to the user, NEVER show the JSON
- Log internal_thought to agent_log for debugging
- The tool execution loop must support MULTIPLE tool_calls per turn (not just [0])
- Feed ALL tool results back to the LLM before the next reasoning step

## LLM Loop Architecture (TypeScript)

```typescript
const MAX_REACT_ITERATIONS = 4;

// ReAct loop
for (let i = 0; i < MAX_REACT_ITERATIONS; i++) {
  const response = await callLLM(systemPrompt, messages);
  
  // Log internal_thought if present
  const thought = extractInternalThought(response.content);
  if (thought) await logAgent(clientId, "internal_thought", JSON.stringify(thought));
  
  // If no tool calls → agent is done reasoning, return text
  if (!response.tool_calls?.length) {
    return extractClientResponse(response.content); // strip internal_thought JSON
  }
  
  // Execute ALL tool calls in this turn
  const toolResults = [];
  for (const tc of response.tool_calls) {
    const result = await executeTool(env, clientId, tc);
    toolResults.push({ tool_call_id: tc.id, content: JSON.stringify(result) });
  }
  
  // Feed results back for next reasoning step
  messages.push({ role: "assistant", content: response.content, tool_calls: response.tool_calls });
  for (const tr of toolResults) {
    messages.push({ role: "tool", content: tr.content, tool_call_id: tr.tool_call_id });
  }
}

// Max iterations reached
return "Processing in progress, I'll get back to you shortly.";
```

## Helper: Extract internal_thought from response

```typescript
function extractInternalThought(content: string): any | null {
  const match = content.match(/```json\s*(\{[\s\S]*?"internal_thought"[\s\S]*?\})\s*```/);
  if (match) {
    try { return JSON.parse(match[1]).internal_thought; } catch {}
  }
  // Also try inline JSON
  const inlineMatch = content.match(/\{[\s\S]*?"internal_thought"[\s\S]*?\}/);
  if (inlineMatch) {
    try { return JSON.parse(inlineMatch[0]).internal_thought; } catch {}
  }
  return null;
}
```

## Implementation Pitfalls (learned from Scena production deployment)

### 1. Async tool detection — stop the loop
Some tools (generate_image, generate_video, generate_voice) are ASYNC: they submit to an external API and the result arrives later via webhook. When the agent calls one of these, STOP the ReAct loop immediately — don't wait for a result that won't come in this request.

```typescript
const hasAsyncTool = response.tool_calls.some(
  tc => ["generate_image", "generate_video", "generate_voice"].includes(tc.function.name)
);
if (hasAsyncTool) {
  finalResponse = toolResults[0]?.telegram_message || "Processing...";
  break; // Stop ReAct loop
}
```

### 2. Parse internal_thought from BOTH formats
LLMs are inconsistent. They might put the JSON in a fenced code block OR inline. Your parser must handle both:

```typescript
// Try fenced first: ```json { ... } ```
const fencedMatch = content.match(/```json\s*(\{[\s\S]*?\})\s*```/);
// Then inline: { "internal_thought": { ... } }
const inlineMatch = content.match(/\{\s*"internal_thought"\s*:\s*\{[\s\S]*?\}\s*\}/);
```

### 3. Strip internal_thought from user-facing response
The parsed thought must be LOGGED but REMOVED from what the user sees. The `cleanContent` after stripping the JSON block is what gets sent to the client.

### 4. Max iteration fallback
If the agent exhausts all iterations without producing a text response, return a graceful fallback message — don't leave the user with silence or raw tool output.

### 5. tool_choice: "auto" vs "required"
Use `"auto"` — the agent should be allowed to respond with plain text (consultation mode) without forcing a tool call. `"required"` breaks the vague-message detection pattern.

### 6. Feed ALL tool results, not just the first
Old pattern: `tool_calls[0]` only. New: loop through ALL tool_calls, execute each, collect all results, feed them all back as separate `role: "tool"` messages. This enables multi-tool turns (e.g., validate + generate in parallel).

### 7. Debugging: systematic test suite for agent + security
When refactoring a ReAct agent, build an 8-phase test suite:
1. **Structure** — files exist, min sizes, no empty dirs
2. **Bug hunt** — search for placeholder tokens (`***`, `TODO`, `FIXME`) in SQL queries
3. **Schema consistency** — every column referenced in code must exist in CREATE TABLE
4. **ReAct architecture** — loop exists, parser works, all tools implemented, results fed back
5. **Security** — no secrets in frontend, CORS whitelist, webhook signatures, rate limiting
6. **Endpoints** — all routes registered, admin sub-routes covered
7. **Config** — no keys in wrangler.toml, D1 bindings present

### 8. Security hardening checklist for Cloudflare Workers
- **Stripe webhook**: verify `Stripe-Signature` header using HMAC-SHA256 with `crypto.subtle`
- **CORS**: define `ALLOWED_ORIGINS` array, check `Origin` header, return empty string if not in list
- **Rate limiting**: query `agent_log` table with time window (D1-based, free tier compatible)
- **Admin auth**: never hardcode secrets in static HTML. Use login endpoint → HMAC token with expiry → sessionStorage
- **Token validation**: `base64(role:expires).hmac_hex` pattern, verify both signature and expiry

## When to Use

- Agent needs to decide between consultation vs execution
- Multi-step workflows where intermediate results affect next steps
- Error recovery requires autonomous re-planning
- User provides vague input that needs clarification before action
- Agent needs to self-correct (wrong ratio → resize → retry)

## When NOT to Use

- Simple single-turn Q&A
- Deterministic pipelines with no branching
- Latency-critical paths (each LLM call adds ~1-3s)
- When all tools are async anyway (no observation loop needed)
