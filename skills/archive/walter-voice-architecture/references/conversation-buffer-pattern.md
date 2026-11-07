# Voice Router Conversation Buffer

## Problem (2026-05-19)

Lucas asked Gemini Live about the "nouveau modèle 3D de Microsoft". Gemini Live recalled memory, answered. Then Lucas said "Mener une analyse approfondie." Gemini Live escalated to Hermes async, but ONLY passed "Mener une analyse approfondie" — NOT the Microsoft 3D context.

Hermes responded: "Monsieur, la demande d'analyse est arrivée sans sujet défini."

## Root Cause

Gemini Live treats each tool call as isolated. When it calls `voice_router`, it only passes the current `user_utterance`, not the conversation history. The voice_router then builds a prompt for Hermes with just the utterance, no context.

## Solution: ConversationBuffer

```python
class ConversationBuffer:
    """Tracks recent messages per voice session for context-aware escalation."""
    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._buffers: dict[str, collections.deque] = {}

    def add(self, call_id: str, role: str, text: str):
        if call_id not in self._buffers:
            self._buffers[call_id] = collections.deque(maxlen=self.max_turns)
        if text.strip():
            self._buffers[call_id].append((role, text.strip()))

    def get_context(self, call_id: str, last_n: int = 6) -> str:
        buf = self._buffers.get(call_id)
        if not buf:
            return ""
        lines = []
        for role, text in list(buf)[-last_n:]:
            label = "Monsieur" if role == "user" else "W.Alter"
            lines.append(f"{label}: {text}")
        return "\n".join(lines)
```

## Integration Points

1. **RouteRequest** — added `call_id: str` and `assistant_response: str` fields
2. **route()** — at entry, `conversation_buffer.add(call_id, "user", q)`
3. **route_endpoint()** — after response, `conversation_buffer.add(call_id, "assistant", spoken_response)`
4. **build_deep_prompt()** — injects `conversation_buffer.get_context(call_id, last_n=6)` into Hermes prompt
5. **app.js normalizeToolCallArgs()** — passes `state.callId` to voice_router

## Result

Hermes now receives:
```
Contexte de la conversation vocale en cours:
Monsieur: Tu as entendu parler du nouveau modèle 3D de Microsoft ?
W.Alter: Monsieur, je n'ai pas d'informations sur un nouveau modèle 3D Microsoft...
Monsieur: Mener une analyse approfondie.
```

Hermes can now correctly infer that the "analyse approfondie" is about the Microsoft 3D model.

## Version

voice-router-v1.3-conversation-buffer
