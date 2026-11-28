"""Host-independent hard input blocks, pinned from the installed Cua tool.

Origin: NousResearch/hermes-agent tools/computer_use/tool.py; LICENSE.hermes.
This boundary is also checked by the host adapter before central approval.
"""
import re
from typing import Any, Dict, Optional

_BLOCKED_KEY_COMBOS = {
    frozenset({"cmd", "shift", "backspace"}), frozenset({"cmd", "option", "backspace"}),  # empty trash / force delete
    frozenset({"cmd", "ctrl", "q"}), frozenset({"cmd", "shift", "q"}),                    # lock screen / log out
    frozenset({"cmd", "option", "shift", "q"}), frozenset({"win", "l"}),                  # force log out / lock
    frozenset({"ctrl", "option", "delete"}), frozenset({"ctrl", "option", "del"}), frozenset({"option", "f4"}),
}
_KEY_ALIASES = {"command": "cmd", "control": "ctrl", "alt": "option", "⌘": "cmd", "⌥": "option",
                "windows": "win", "super": "win", "meta": "win"}
_BLOCKED_TYPE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (  # dangerous shell patterns for `type` (last one: fork bomb)
    r"curl\s+[^|]*\|\s*bash", r"curl\s+[^|]*\|\s*sh", r"wget\s+[^|]*\|\s*bash",
    r"\bsudo\s+rm\s+-[rf]", r"\brm\s+-rf\s+/\s*$", r":\s*\(\)\s*\{\s*:\|:\s*&\s*\}")]

def _canon_key_combo(keys: str) -> frozenset:
    # Split on "+" AND "-": cua-driver accepts hyphenated combos, so "ctrl-alt-delete" would bypass otherwise.
    return frozenset(_KEY_ALIASES.get(p, p) for p in (q.strip().lower() for q in re.split(r"\s*[+\-]\s*", keys)) if p)

def reject_unsafe(action: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """JSON error for hard-blocked input, else None. Runs BEFORE the approval prompt."""
    if action == "type" and (pat := next((p.pattern for p in _BLOCKED_TYPE_PATTERNS if p.search(args.get("text", ""))), None)):
        return {"error": f"blocked pattern in type text: {pat!r}",
                           "hint": "Dangerous shell patterns cannot be typed via computer_use."}
    if action == "key" and (blocked := next((b for b in _BLOCKED_KEY_COMBOS
                                             if b.issubset(_canon_key_combo(args.get("keys", "")))), None)) is not None:
        return {"error": f"blocked key combo: {sorted(blocked)}", "hint": "Destructive system shortcuts are hard-blocked."}
    if args.get("bring_to_front") and args.get("delivery_mode") != "foreground":
        return {"error": "bring_to_front requires delivery_mode='foreground'",
                           "code": "bring_to_front_requires_foreground"}
    return None
