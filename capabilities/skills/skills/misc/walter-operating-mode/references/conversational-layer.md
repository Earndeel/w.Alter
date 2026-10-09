# Conversational Communication Layer — Implementation Reference

The conversational layer lives in `voice_router_service.py`. It post-processes text-channel responses to sound like natural conversation.

## Key Functions

### `_conversational_wrap(res: RouteResponse, req: RouteRequest) -> RouteResponse`
Called in `route_endpoint()` after `route()` returns. Applies conversational synthesis only when:
- `req.source` is in `TEXT_CHANNELS` = `{"telegram", "browser", "api"}`
- `res.route` is in `_ROUTES_TO_WRAP` = `{"context_lookup", "quick_web_brave", "quick_web_live_grounding", "task_status", "store_memory", "notify"}`
- `res.route` is NOT in `_ROUTES_THAT_SPEAK_NATURALLY` = `{"direct_answer_flash_lite"}`
- `TECHNICAL_DETAIL_CUES` does NOT match the user utterance (user didn't explicitly ask for raw detail)
- `full_report` has content worth converting (>50 chars)

Uses `synthesize_for_chat()` to convert `full_report` into a natural `spoken_response`.

### `synthesize_for_chat(query, material, channel) -> Summary`
Calls Gemini Flash Lite with `CHAT_COMMUNICATION_CONTEXT` as the system prompt. Converts technical output into natural conversational French. Returns a `Summary` with `spoken_summary`, `decision`, `next_action`, `confidence`.

### `CHAT_COMMUNICATION_CONTEXT`
System prompt that enforces:
- NEVER code, logs, JSON, stack traces, markdown, or technical data
- NEVER bullet lists, tables, or technical formatting
- Explain essentials in simple French
- Max 120 words, 1-2 sentences

## Technical Detail Bypass

`TECHNICAL_DETAIL_CUES` = regex matching:
- `montre-moi le code`, `affiche les logs`, `donne-moi le détail`, `fais voir le code`
- `show.*code`, `technical`, `technique`, `raw`, `brut`
- `pas de résumé`, `donne moi tout`, `détail technique`, `rapport complet`, `full report`
- `montre-moi les logs`, `code complet`, `fichier`, `script`, `commit`, `diff`

When any of these match, `_conversational_wrap` passes through verbatim.

## Voice vs Text Distinction

- **Voice channels** (source=`voice`): use `synthesize_for_voice()` — optimized for spoken brevity, short sentences
- **Text channels** (source=`telegram`, `browser`, `api`): use `synthesize_for_chat()` — natural conversation, conversational tone

Voice channels are NOT wrapped by `_conversational_wrap` at all — they already have their own synthesis path in the route functions (`synthesize_for_voice()` is called by `hindsight_context_lookup()` and `quick_web_search()`).

## outer_router.py Integration

`_format_response()` in `outer_router.py`:
- For `direct_answer_flash_lite`: returns just `spoken_response` — no labels
- For other routes: appends "Décision:" and "Action:" labels (useful context since the text is already conversational from the wrap)

## Files Involved

- `/root/.hermes/services/voice_router_service.py` — `_conversational_wrap()`, `synthesize_for_chat()`, `CHAT_COMMUNICATION_CONTEXT`, `TECHNICAL_DETAIL_CUES`, `TEXT_CHANNELS`
- `/root/.hermes/hermes-agent/gateway/outer_router.py` — `_format_response()` direct_answer bypass
