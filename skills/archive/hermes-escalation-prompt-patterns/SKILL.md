---
name: hermes-escalation-prompt-patterns
description: "Prompt design patterns for Hermes escalation from voice/external sessions — avoid identity redundancy, lean context injection, response flow tracing."
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [voice, hermes, prompts, escalation, gemini-live]
---

# Hermes Escalation Prompt Patterns

How to build escalation prompts when external interfaces (Gemini Live, Telegram bots, etc.) hand off to Hermes for deep processing.

## Core Principle

Hermes already has its full system payload (SOUL.md, system prompt, identity). The escalation prompt tells Hermes **WHERE** the request comes from and provides **CONVERSATION CONTEXT**. It does NOT tell Hermes **WHO** it is.

## Anti-Pattern: Identity Redundancy

**Wrong** (initial build, corrected 2026-06-09):
```
Tu es W.Alter, le majordome numérique de Monsieur...
[full identity preamble]
Voici la requête de Monsieur...
```

**Why wrong:**
- Redundant tokens — Hermes system prompt already has this
- Can cause conflicting instructions if wording diverges
- Wastes context window on known information

## Correct Prompt Structure

```
[Appel deep via Gemini Live — session <call_id>]
Réponds de manière concise et directe.

Contexte de la conversation vocale en cours:
[HH:MM] Monsieur: <verbatim utterance>
[HH:MM] W.Alter: <spoken response>
[HH:MM] Monsieur: <next utterance>
...

Session active depuis <duration>. Requête finale: <final user request>
```

**Fields:**
- Source identifier: tells Hermes this came from voice (not Telegram, not TUI)
- Instruction: concise and direct (voice context = user expects quick answer)
- Timestamped conversation turns: provides temporal flow and topic evolution
- Session metadata: duration, turn count for context richness
- Final request: the actual thing Hermes needs to do

## Response Flow (Hermes User's Ears)

```
hermes chat -Q → stdout (SPOKEN_SUMMARY, ~400 chars)
  → voice_router_service.py parses stdout
  → synthesize_for_voice(Gemini API, ~400-600ms)
  → POST https://127.0.0.1:8765/internal/job-complete (HTTPS!)
  → server.py broadcasts to WebSocket clients
  → app.js jobResultQueue (FIFO, per-job tracking)
  → drainQueue() wraps result:
     "Dis maintenant à voix haute et de manière concise: ..."
  → client.sendTextMessage(wrapped_prompt)
  → Gemini Live TTS → user hears response
```

**Key:** Hermes never speaks directly. Browser-side JS prompts Gemini Live to verbalize the response naturally.

## Session Continuity via --resume

```bash
# First call — no session yet
hermes chat -Q "request" 2>&1 | tee /tmp/hermes_out.txt
# stderr contains: session_id: abc123

# Subsequent calls — resume same session
hermes chat -Q --resume abc123 "follow-up request"
```

**Parsing session_id from stderr:**
```python
import re
match = re.search(r'session_id:\s*(\S+)', stderr_output)
if match:
    session_id = match.group(1)
```

## ConversationBuffer (voice_router_service.py)

Tracks conversation context per `call_id` for multi-turn voice sessions.

**v1.4 features (2026-06-09):**
- Timestamps `(HH:MM)` per turn
- `get_context_summary(call_id)` — structured metadata
- `get_context(call_id, last_n=8)` — expanded window
- Duration tracking via `_call_starts[call_id]`
- LRU eviction (max 10 concurrent calls)

## Pitfalls

- **Never duplicate Hermes identity** in escalation prompts — Hermes system prompt handles this
- **HTTPS for internal calls** — `voice_router → server.py` must use `https://127.0.0.1:8765` with `verify=False`. HTTP fails silently.
- **Stripping technical output** — `synthesize_for_voice` must strip JSON/logs/code before relay. Raw technical output in TTS is unintelligible.
- **Session_id parsing** — `-Q` mode prints `session_id:` to stderr, not stdout. Capture stderr separately.
