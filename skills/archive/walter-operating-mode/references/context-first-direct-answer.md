# Context-First Direct Answer — Reference

## Principle
Before calling any search/recall/query tool, check if the answer is already present in the **current session context** (prior turns, tool results, current files, active task list).

## Why this matters
A session that contains the answer but triggers external tools anyway causes:
- Token waste on identical queries
- User frustration ("I already told you this")
- Risk of hitting rate limits or tool-loop warnings

## Practical examples

**Example 1 — Fallback providers already configured**
```
User: "What are the different fallback models?"
Context: In the previous turn, the agent listed: fallback 1 = nvidia/moonshotai/kimi-k2.6; fallback 2 = opencode/mimo-v2.5-free.
Right answer: Repeat them directly.
Wrong answer: Call session_search, web_search, hindsight_recall, etc. with the same query.
```

**Example 2 — Curator settings already reviewed**
```
User: "Why hasn't the Curator deleted those 12 unused skills?"
Context: Earlier in the same session, the agent found that consolidate: false and stale threshold = 30 days.
Right answer: Summarize those findings directly.
Wrong answer: Re-query config.yaml or the database.
```

## How to check
1. Scan the current turn history for the same or equivalent question.
2. Look at tool results already returned in this session.
3. If the data is there, extract and present it without further tools.

## When it is OK to re-query
- The user explicitly asks for a *fresh* or *real-time* check.
- The session context is stale or was invalidated by a later operation.
- The user is asking a follow-up that requires new data (e.g. "has it changed since then?").

## Related skill
See also `agent-loop-prevention` for the anti-pattern "Redundant context re-querying". Both skills describe the same failure mode from complementary angles.
