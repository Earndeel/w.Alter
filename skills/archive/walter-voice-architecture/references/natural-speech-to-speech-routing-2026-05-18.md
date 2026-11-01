# Natural speech-to-speech routing — 2026-05-18

Session learning for W.Alter voice architecture.

## Goal
Make voice conversation feel continuous while still routing complex work to Hermes.

## Durable pattern
Use a two-path voice stack:

1. Fast path: Gemini 3.1 Flash Live answers directly for simple, stable, non-personal, non-current, non-action requests.
2. Deep path: Gemini Live calls `voice_router` for personal data, memory, current web, system/logs, code/files, credentials, side effects, long reasoning, or ambiguous action requests.

The user experience rule is more important than the implementation detail: no artificial pause, no mention of tools/routes/JSON/job IDs unless explicitly asked.

## Prompt rules to embed in voice layer
- Address the user as "Monsieur", never by first name.
- If a tool call may take more than about one second, speak a micro-ack first: "Je vérifie, Monsieur." or "Je m'en occupe, Monsieur."
- After tool completion, speak one natural sentence; do not expose tool mechanics.
- For async Hermes jobs, say that the deep brain is handling it and that conversation can continue; only read the job_id if the user asks.
- Keep normal voice responses to 1–3 sentences.

## Implementation findings
- Browser-based Gemini Live must identify itself to the backend as `source="voice"`, not `source="browser"`; otherwise the router may apply text-channel conversational wrapping, adding latency and odd paraphrases.
- Keep Live thinking low for conversational responsiveness (`THINKING_LEVEL = "low"`) unless a specific test requires deeper Live-side reasoning.
- Sanitize every route response before Gemini Live can read it: `spoken_response`, `decision`, `next_action`, `full_report`, and nested `data`. Old job records may contain stale names or raw technical content.
- Add a runtime-load smoke test for browser JS, not just `node --check`; syntax checks miss runtime hazards such as a stray `async` identifier before a comment.

## Reliability findings
- Voice jobs should prefer the default Hermes orchestrator unless a specialized profile is proven healthy. Stale worker profiles with bad credentials create failed voice jobs and break the speech loop.
- If profile names like `research`, `coder`, `hephaestus`, or `prometheus` are accepted by the router, normalize them through a safe alias table and keep fallback to `default`.
- Health checks should cover service status, ports, `/health` for voice-call, `/health` for voice-router, JS syntax/runtime load, and a route probe for both direct-answer and task-status paths.

## Regression probes
- Direct simple request should return `direct_answer_flash_lite` quickly and without tool leakage.
- Job status should return instantly, not trigger text wrapping.
- Serialized route output must not contain the user's first name.
- Browser app JS should load in a minimal mocked runtime without throwing.