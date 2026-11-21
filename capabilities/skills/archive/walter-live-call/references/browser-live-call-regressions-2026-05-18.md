# Voice-call practical regressions — 2026-05-18

Practical notes for the browser Gemini Live call app and voice-router services.

## Bugs/quirks worth preserving
- `node --check static/app.js` is not enough. It catches syntax errors but not runtime hazards. A stray token such as `async // comment` can pass syntax checking and then throw `ReferenceError: async is not defined` when the browser evaluates the script.
- Add a minimal runtime-load smoke test when changing browser voice JS: mock `window`, `document`, tool classes, `GeminiLiveAPI`, audio helpers, then `require()`/evaluate `static/app.js` and ensure it loads without throwing.
- Cache-bust `index.html` script versions after JS changes; otherwise the browser may keep stale app/tool logic.

## Natural call behavior
- Use `source="voice"` for browser Live tool calls to the backend. Treating this as `browser` can invoke text-channel wrapping, adding latency and unnatural phrasing.
- For tool confirmations, nudge Gemini Live quickly (~500 ms) after tool completion if it has not spoken yet.
- Do not freeze or expose mechanics: the spoken result should be one natural sentence and must not mention tools, routes, JSON, or job IDs unless asked.

## Service verification sequence
- Compile/check Python: voice-call server, voice-router service, SIP bridge if touched.
- Check browser JS syntax and runtime load.
- Restart `voice-router.service`, `hermes-voice-call.service`, and `hermes-bridge.service` only after validation.
- Verify `/health` for both voice-call and voice-router.
- Probe `/route` with one direct-answer utterance and one task-status utterance.
- Confirm serialized output does not leak the user's first name and that status responses do not re-summarize stale job internals unless requested.