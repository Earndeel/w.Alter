#!/usr/bin/env bash
# Restore W.Alter TUI design after hermes update
# Usage: hermes update && bash ~/.hermes/scripts/restore-tui-design.sh
set -e

REPO="/root/.hermes/hermes-agent"
OVERRIDE_DIR="$HOME/.hermes/tui-overrides"

echo "[restore-tui] Restoring custom TUI design..."

# Copy known-safe overrides
cp "$OVERRIDE_DIR/branding.tsx" "$REPO/ui-tui/src/components/branding.tsx"
cp "$OVERRIDE_DIR/appLayout.tsx" "$REPO/ui-tui/src/components/appLayout.tsx"
cp "$OVERRIDE_DIR/messageLine.tsx" "$REPO/ui-tui/src/components/messageLine.tsx"
cp "$OVERRIDE_DIR/details.ts" "$REPO/ui-tui/src/domain/details.ts"
cp "$OVERRIDE_DIR/types.ts" "$REPO/ui-tui/src/types.ts"
cp "$OVERRIDE_DIR/thinking.tsx" "$REPO/ui-tui/src/components/thinking.tsx"
cp "$OVERRIDE_DIR/markdown.tsx" "$REPO/ui-tui/src/components/markdown.tsx"
cp "$OVERRIDE_DIR/createGatewayEventHandler.ts" "$REPO/ui-tui/src/app/createGatewayEventHandler.ts"
cp "$OVERRIDE_DIR/gatewayTypes.ts" "$REPO/ui-tui/src/gatewayTypes.ts"
cp "$OVERRIDE_DIR/platform.ts" "$REPO/ui-tui/src/lib/platform.ts"
cp "$OVERRIDE_DIR/openExternalUrl.ts" "$REPO/ui-tui/src/lib/openExternalUrl.ts"

# Patch backend: inject recent_sessions into _session_info
echo "[restore-tui] Patching backend..."
python3 << 'PYEOF'
import re, sys

path = "/root/.hermes/hermes-agent/tui_gateway/server.py"
with open(path, "r") as f:
    content = f.read()

marker = '    try:\n        from hermes_cli.banner import get_update_result\n        from hermes_cli.config import recommended_update_command\n\n        info["update_behind"] = get_update_result(timeout=0.5)\n        info["update_command"] = recommended_update_command()\n    except Exception:\n        pass\n    return info'

replacement = '''    try:
        from hermes_cli.banner import get_update_result
        from hermes_cli.config import recommended_update_command

        info["update_behind"] = get_update_result(timeout=0.5)
        info["update_command"] = recommended_update_command()
    except Exception:
        pass
    # Recent sessions for the welcome panel (TUI only)
    try:
        db = _get_db()
        if db:
            current_sid = getattr(agent, "session_id", None)
            sessions = db.list_sessions_rich(
                source="tui",
                limit=7,  # fetch 7 to exclude current, show 6
            )
            recent = []
            for s in sessions:
                if s.get("id") == current_sid:
                    continue
                if len(recent) >= 6:
                    break
                recent.append({
                    "id": s.get("id", ""),
                    "title": s.get("title") or ((s.get("preview") or "")[:30] + "…") or "—",
                    "preview": (s.get("preview") or "")[:50],
                    "last_active": s.get("last_active") or s.get("started_at") or 0,
                    "message_count": s.get("message_count") or 0,
                    "source": s.get("source") or "",
                })
            info["recent_sessions"] = recent
    except Exception:
        pass
    return info'''

if marker in content:
    content = content.replace(marker, replacement)
    with open(path, "w") as f:
        f.write(content)
    print("[restore-tui] Backend patched OK (recent_sessions).")
else:
    print("[restore-tui] WARNING: backend patch marker not found. Skipping.", file=sys.stderr)

# Patch 2: include todos in every tool.complete so the live todo panel stays fresh
todo_marker = '''    if name == "todo":
        try:
            data = json.loads(result)
            if isinstance(data, dict) and isinstance(data.get("todos"), list):
                payload["todos"] = data.get("todos")
        except Exception:
            pass
    try:'''

todo_replacement = '''    if name == "todo":
        try:
            data = json.loads(result)
            if isinstance(data, dict) and isinstance(data.get("todos"), list):
                payload["todos"] = data.get("todos")
        except Exception:
            pass
    else:
        # Always include current agent todos so the TUI live todo panel
        # stays fresh even when the agent doesn't explicitly call todo.
        agent = session.get("agent") if session else None
        if agent is not None:
            try:
                todo_store = getattr(agent, "_todo_store", None)
                if todo_store is not None:
                    current_todos = todo_store.read()
                    if current_todos:
                        payload["todos"] = current_todos
            except Exception:
                pass
    try:'''

if todo_marker in content:
    content = content.replace(todo_marker, todo_replacement)
    with open(path, "w") as f:
        f.write(content)
    print("[restore-tui] Backend patched OK (todos in tool.complete).")
else:
    print("[restore-tui] WARNING: todo patch marker not found. Skipping.", file=sys.stderr)
PYEOF

# Rebuild TUI
cd "$REPO/ui-tui"
if ! npm run build 2>&1 | tail -5; then
    echo "[restore-tui] ERROR: TUI build failed. Manual fix required."
    exit 1
fi

# Reinstall Python package (editable)
python3 -m pip install --break-system-packages --no-deps -e "$REPO" 2>&1 | tail -3

echo "[restore-tui] Done."
