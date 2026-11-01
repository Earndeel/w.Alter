# Voice Router Conversation Context Fix (2026-05-26)

## Problem
`decide_fast_route()` in `voice_router_service.py` was not passing the conversation buffer context to Gemini Flash Lite when deciding routing. This caused follow-up questions within the same voice call to be treated as standalone questions.

## Symptom
1. User: "check mes mails" → `hermes_async` (correct, escalated to Hermes)
2. User: "les spam, ils viennent d'où ?" → `direct_answer_flash_lite` (WRONG — generic spam lecture instead of understanding it was about HIS emails from the first request)
3. User: frustrated, says the system lost context

## Root Cause
The `decide_fast_route()` function builds a prompt for Gemini Flash Lite with `recent_context` but did NOT include the conversation buffer (`conversation_buffer.get_context()`). Flash Lite saw the question in isolation and judged it "simple enough" for a direct answer.

The conversation buffer was only injected in `build_deep_prompt()` (for hermes_async jobs), not in the routing decision itself.

## Fix
In `decide_fast_route()` (line ~387):
1. Add conversation buffer retrieval:
```python
conv_context = ""
if req.call_id:
    conv_context = conversation_buffer.get_context(req.call_id, last_n=6)
```

2. Inject into the Flash Lite prompt:
```
Contexte de la conversation vocale en cours:
{conv_context or '(aucun — première interaction)'}
```

3. Add routing constraint:
```
- Si la conversation montre que Monsieur parle d'un sujet qui nécessite des outils (emails, messages, données perso), toute question de suivi doit aller dans la MÊME route (hermes_async), jamais direct_answer.
```

## Limitation
Each follow-up still creates a **separate Hermes job** (different session_id). The conversation context is passed via the prompt, not as a true persistent session. This covers 90% of cases but doesn't give Hermes memory of what it already found in the first job.

## Key insight
The voice router has TWO decision points:
1. **Regex cues** (LOG_CUES, DEEP_CUES, etc.) — deterministic, fast
2. **`decide_fast_route()`** — Gemini Flash Lite triage

The regex cues don't need conversation context (they match keywords). But the Flash Lite triage absolutely does — without context, it can't distinguish "what are spams?" (generic, direct_answer) from "where do the spams in my inbox come from?" (follow-up about emails, needs hermes_async).

## Files
- `/root/.hermes/services/voice_router_service.py` — `decide_fast_route()` function
