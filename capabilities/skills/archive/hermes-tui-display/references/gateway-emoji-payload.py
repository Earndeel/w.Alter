# Gateway tool_start emoji fix — tui_gateway/server.py _on_tool_start()
# The emoji must be explicitly fetched and included in the payload.

# BEFORE (no emoji sent):
if _tool_progress_enabled(sid):
    payload = {
        "tool_id": tool_call_id,
        "name": name,
        "context": _tool_ctx(name, args),
    }

# AFTER (emoji from registry):
if _tool_progress_enabled(sid):
    emoji = ""
    try:
        from agent.display import get_tool_emoji
        emoji = get_tool_emoji(name, "")
    except Exception:
        pass
    payload = {
        "tool_id": tool_call_id,
        "name": name,
        "context": _tool_ctx(name, args),
    }
    if emoji:
        payload["emoji"] = emoji
