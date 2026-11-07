#!/usr/local/bin/walter-python
"""Walter Memory disclosure check where a message leaves (P1.7) — host adapter for Claude Code (PreToolUse on the
sending tools) and Hermes (shell hook pre_tool_call, matcher send_message).

  disclosure_hook.py claude-code   stdin: Claude Code hook JSON → stdout: permissionDecision ask|deny (or nothing)
  disclosure_hook.py hermes        stdin: Hermes shell-hook JSON → stdout: {"action": "block"|"approve", "message"}
A failure of the check itself never lets an unchecked commitment through silently: Claude Code then asks, Hermes
asks for approval. Decisions are journaled in system.audit_log (never the text).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "claude-code"
    try:
        ev = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    try:
        from walter_memory import disclosure
        out = disclosure.claude_code_hook(ev) if host == "claude-code" else disclosure.hermes_hook(ev)
    except Exception as e:  # noqa: BLE001 — the check failed: ask the owner rather than send blind
        msg = f"Contrôle de divulgation Walter indisponible ({type(e).__name__}) : accord de Monsieur requis."
        out = ({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                       "permissionDecisionReason": msg}} if host == "claude-code"
               else {"action": "approve", "message": msg, "rule_key": "walter-disclosure"})
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
