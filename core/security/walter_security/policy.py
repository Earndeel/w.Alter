"""One execution policy for every path that runs a tool (lot E3): the engine (policy.mjs, same rules, same test
vectors) and the MCP server backstop for every client. Pure: no I/O but reading policy.json and resolving symlinks.

decide(policy, tool=, args=, interface=, depth=) → {"decision": allow|check|ask|deny, "class", "reason", "rule"}
`check` = the caller runs Memory's disclosure check on the outgoing message (allow | ask | block).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / "policy.json"
ORDER = ("allow", "check", "ask", "deny")


def strictest(*decisions: str) -> str:
    return max(decisions, key=ORDER.index)


def _glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    if pattern.startswith("**/"):
        out, i = "(?:^|.*/)", 3
    while i < len(pattern):
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"$")


def _name_re(pattern: str) -> re.Pattern:
    return re.compile("^" + ".*".join(re.escape(p) for p in pattern.split("*")) + "$")


@lru_cache(maxsize=4)
def _compiled(path: str, instance_root: str) -> dict:
    p = json.loads(Path(path).read_text())
    sub = lambda g: g.replace("@instance", instance_root.rstrip("/")) if instance_root else g  # noqa: E731
    never = p["never"]
    p["_never_paths"] = [_glob_re(sub(g)) for g in never["paths"] if instance_root or "@instance" not in g]
    p["_path_allow"] = [_glob_re(g) for g in never.get("path_allow", [])]
    p["_never_cmds"] = [re.compile(c) for c in never.get("commands", [])]
    p["_classes"] = [(cls, [_name_re(n) for n in names]) for cls, names in p["classes"].items()]
    return p


def load(path: str | Path = POLICY, instance_root: str | None = None) -> dict:
    if instance_root is None:
        instance_root = os.environ.get("WALTER_INSTANCE_ROOT") or _instance_root()
    return _compiled(str(path), instance_root or "")


def _instance_root() -> str:
    try:
        return Path("/etc/walter/instance").read_text().strip()
    except OSError:
        return ""


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


TOKEN = re.compile(r"""[\s'"`;|&<>()=,]+""")


def _candidates(text: str, home: str) -> list[str]:
    out = []
    for tok in TOKEN.split(text):
        if not tok or ("/" not in tok and not tok.startswith(".")):
            continue
        if tok.startswith("~/"):
            tok = home.rstrip("/") + tok[1:]
        out.append(tok)
        real = os.path.realpath(tok) if tok.startswith("/") else None
        if real and real != tok:
            out.append(real)
    return out


def _protected(p: dict, path: str) -> str | None:
    if any(r.search(path) for r in p["_path_allow"]):
        return None
    for g, r in zip(p["never"]["paths"], p["_never_paths"]):
        if r.search(path):
            return g
    return None


def _matches(patterns, name: str) -> bool:
    return any(r.match(name) for r in patterns)


def classify(p: dict, tool: str) -> str:
    for cls, patterns in p["_classes"]:
        if _matches(patterns, tool):
            return cls
    return "unknown"


def decide(p: dict, *, tool: str, args=None, interface: str = "api", depth: int = 0, home: str = "/root") -> dict:
    args = args if isinstance(args, dict) else {}
    if tool == "mcp__walter__walter_call" and args.get("tool"):        # the generic door is judged as what it opens
        tool, args = f"mcp__walter__{args['tool']}", (args.get("arguments") or {})
    cls = classify(p, tool)
    base = {"class": cls, "tool": tool}
    if cls == "delegate" and depth >= int(p["never"].get("max_depth", 3)):
        return {**base, "decision": "deny", "rule": "never.max_depth",
                "reason": f"délégation refusée : profondeur maximale ({p['never'].get('max_depth', 3)}) atteinte"}
    # a shell command is read whole; any other tool only by its path arguments (a note that names a file is not access)
    texts = _strings(args) if cls == "shell" else [s for k in p.get("path_keys", []) for s in _strings(args.get(k))]
    for text in texts:
        for cand in _candidates(text, home):
            g = _protected(p, cand)
            if g:
                return {**base, "decision": "deny", "rule": f"never.paths:{g}",
                        "reason": "refusé : fichier de secrets ou d'accès (jamais lu ni écrit par un agent ; passer par walter-secret exec)"}
    if cls == "shell":
        for text in (s for k in p.get("shell_text_keys", []) for s in _strings(args.get(k))):
            for raw, r in zip(p["never"]["commands"], p["_never_cmds"]):
                if r.search(text):
                    return {**base, "decision": "deny", "rule": f"never.commands:{raw}",
                            "reason": "refusé : commande qui révèle un secret (utiliser walter-secret exec --bind, valeurs jamais dans le modèle)"}
    preset_name = p["interfaces"].get(interface, "api")
    preset = p["presets"][preset_name]
    decision = preset.get(cls, preset.get("unknown", "ask"))
    rule = f"preset.{preset_name}.{cls}"
    if depth > 0:
        child = p["presets"]["child"].get(cls, p["presets"]["child"].get("unknown", "ask"))
        if ORDER.index(child) > ORDER.index(decision):
            decision, rule = child, f"preset.child.{cls}"
    reasons = {"allow": "", "check": "contrôle de divulgation avant l'envoi",
               "ask": "action sensible : accord de Monsieur requis", "deny": "refusé par la politique de cette porte"}
    return {**base, "decision": decision, "rule": rule, "reason": reasons[decision]}
