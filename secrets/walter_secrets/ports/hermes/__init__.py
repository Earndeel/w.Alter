"""walter-secrets — W.Alter's autonomous access to Monsieur's Bitwarden (see bwvault.py for the policy).

Tools: secret_search (metadata only), secret_file (decrypted attachment → tmpfs path), secret_reveal (value into the
conversation — last resort). Hooks: placeholders `{{bw:<item>:<field>}}` in ANY tool's arguments are resolved right
before execution (terminal: via `$(walter-secret get …)` so the value never even appears in the arguments), and every
known secret value is masked back into its placeholder in tool results and terminal output.
"""
from __future__ import annotations

import json
import logging
import shlex
from typing import Any

from ...vault import PLACEHOLDER, VAULT, SecretError, audit, cleanup_files
from ...masking import Masker

logger = logging.getLogger("walter-secrets")
OWN_TOOLS = {"secret_search", "secret_file", "secret_reveal", "secret_create_login", "secret_capture_totp", "secret_fill",
             "secret_otp"}
CLI = "/usr/local/bin/walter-secret"
MASKER = Masker(lambda: VAULT.maskable())


def _scrub(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    try:   # values Hermes' vault/bridge registered (passwords, 2FA keys, codes) — Camofox snapshots are not covered by core
        from agent.redact import redact_registered_vault_values
        text = redact_registered_vault_values(text)
    except Exception:
        pass
    return MASKER.scrub(text)


def _resolve(m, tool: str, session: str) -> str:
    ref, field = m.group(1).strip(), m.group(2).strip()
    item = VAULT.find(ref)
    v = VAULT.value(item["id"], field)
    MASKER.register(v, f"{{{{bw:{item['id']}:{field}}}}}")
    audit("use", item, field, tool=tool, session=session)
    return v


def _walk(obj: Any, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: _walk(v, fn) for k, v in obj.items()}
    return obj


# ── hooks ──────────────────────────────────────────────────────────────────────
def _pre_tool_call(tool_name: str = "", args: dict | None = None, session_id: str = "", **_kw):
    if tool_name.startswith("browser_vault_"):
        try:                                   # native model-blind autofill: unlock Bitwarden without a human prompt
            from . import browser_bridge
            browser_bridge.ensure_unlocked()
        except Exception as e:
            logger.warning("walter-secrets: Bitwarden auto-unlock failed: %s", type(e).__name__)
        return None
    if tool_name in OWN_TOOLS or not isinstance(args, dict) or "{{bw:" not in json.dumps(args, ensure_ascii=False):
        return None
    try:
        if tool_name == "terminal" and isinstance(args.get("command"), str):
            def sub(m):
                item = VAULT.find(m.group(1))
                field = m.group(2).strip()
                MASKER.register(VAULT.value(item["id"], field), f"{{{{bw:{item['id']}:{field}}}}}")   # for output masking
                audit("use", item, field, tool="terminal", session=session_id)
                return f"$({CLI} get {shlex.quote(item['id'])} {shlex.quote(field)})"
            return {"action": "modify", "args": {"command": PLACEHOLDER.sub(sub, args["command"])}}
        new = _walk(args, lambda s: PLACEHOLDER.sub(lambda m: _resolve(m, tool_name, session_id), s))
        return {"action": "modify", "args": new}
    except SecretError as e:
        return {"action": "block", "message": f"walter-secrets: {e}"}


def _transform_tool_result(tool_name: str = "", result: Any = None, **_kw):
    if tool_name == "secret_reveal" or not isinstance(result, str):
        return None
    out = _scrub(result)
    return out if out != result else None


def _transform_terminal_output(output: str = "", **_kw):
    out = _scrub(output)
    return out if out != output else None


# ── tools ──────────────────────────────────────────────────────────────────────
def _ok(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _secret_search(args: dict, **kw) -> str:
    try:
        res = VAULT.search(args.get("query") or "", args.get("type"), int(args.get("limit") or 20))
        audit("search", None, None, query=args.get("query"), results=len(res))
        return _ok({"items": res, "usage": "Put {{bw:<id>:<field>}} in any tool argument (terminal: inside double "
                                          "quotes). Fields are listed per item; custom fields as field:<name>."})
    except SecretError as e:
        return _ok({"error": str(e)})


def _secret_file(args: dict, **kw) -> str:
    try:
        item = VAULT.find(args["item"])
        p = VAULT.attachment(item["id"], args.get("attachment"))
        audit("file", item, p.name, session=kw.get("session_id", ""))
        return _ok({"path": str(p), "note": "Decrypted in RAM (/dev/shm), deleted after 2 h. Upload or attach it from "
                                            "this path; read its content only if the task needs it."})
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


def _secret_reveal(args: dict, **kw) -> str:
    try:
        item = VAULT.find(args["item"])
        v = VAULT.value(item["id"], args["field"])
        audit("reveal", item, args["field"], reason=args.get("reason"), session=kw.get("session_id", ""))
        return _ok({"item": item["name"], "field": args["field"], "value": v})
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


SCHEMAS = {
    "secret_search": {
        "name": "secret_search",
        "description": ("Search Monsieur's Bitwarden (all his passwords, API keys, bank cards, identities, document scans). "
                        "Returns metadata only (name, type, username, URLs, card brand/last4, field and attachment names) "
                        "and the item id. To USE a secret, put the placeholder {{bw:<id>:<field>}} in any tool argument "
                        "(terminal command, browser form value, HTTP header…): it is filled in locally at execution and "
                        "masked in results, so the value never enters the conversation. You may use any secret "
                        "autonomously for Monsieur's tasks — no need to ask him."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "words matched against name, username, URL, field/attachment names"},
            "type": {"type": "string", "enum": ["login", "card", "identity", "note", "ssh_key"]},
            "limit": {"type": "integer", "default": 20}}, "required": []}},
    "secret_file": {
        "name": "secret_file",
        "description": ("Decrypt a Bitwarden attachment (passport scan, ID card, contract, certificate…) to a private RAM "
                        "path for upload/attachment. Deleted automatically after 2 hours."),
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string", "description": "item id (from secret_search) or exact name"},
            "attachment": {"type": "string", "description": "file name; optional when the item has one attachment"}},
            "required": ["item"]}},
    "secret_reveal": {
        "name": "secret_reveal",
        "description": ("Return a secret value into the conversation. LAST RESORT: the value is then sent to the model "
                        "provider. Prefer {{bw:<id>:<field>}} placeholders, which work in every tool."),
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string"}, "field": {"type": "string"},
            "reason": {"type": "string", "description": "why the placeholder cannot be used"}},
            "required": ["item", "field", "reason"]}},
}
def _secret_create_login(args: dict, **kw) -> str:
    from . import browser_bridge
    try:
        return _ok(browser_bridge.create_login(username=args["username"], url=args.get("url"), label=args.get("label"),
                                               length=int(args.get("length") or 24), symbols=args.get("symbols", True),
                                               fill=args.get("fill", True), task_id=kw.get("task_id") or "default"))
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


def _secret_capture_totp(args: dict, **kw) -> str:
    from . import browser_bridge
    try:
        return _ok(browser_bridge.capture_totp(handle=args["handle"], task_id=kw.get("task_id") or "default"))
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


SCHEMAS["secret_create_login"] = {
    "name": "secret_create_login",
    "description": ("Create an account for Monsieur: generates a strong password, saves the login in his Bitwarden FIRST "
                    "(folder 'W.Alter – Comptes créés'), then fills the password and confirmation fields of the sign-up "
                    "page open in the browser. The password never enters the conversation. Returns the handle for "
                    "secret_fill on later logins."),
    "parameters": {"type": "object", "properties": {
        "username": {"type": "string", "description": "e-mail or username used for the account (type it into the form yourself)"},
        "url": {"type": "string", "description": "site URL; default = the page open in the browser"},
        "label": {"type": "string", "description": "item name in Bitwarden; default = site host"},
        "length": {"type": "integer", "default": 24},
        "symbols": {"type": "boolean", "default": True, "description": "false if the site rejects special characters"},
        "fill": {"type": "boolean", "default": True}}, "required": ["username"]}}
SCHEMAS["secret_capture_totp"] = {
    "name": "secret_capture_totp",
    "description": ("During a 2FA (authenticator app) setup: reads the key shown on the current page (otpauth link or "
                    "text secret — click 'can't scan / show key' first if only a QR code is shown) and stores it in the "
                    "Bitwarden login, so every future code is generated automatically. Then call "
                    "secret_fill(handle, field='totp') to confirm the setup."),
    "parameters": {"type": "object", "properties": {"handle": {"type": "string", "description": "bw:<id> from secret_create_login or browser_vault_list"}},
                   "required": ["handle"]}}
def _secret_fill(args: dict, **kw) -> str:
    from . import browser_bridge
    try:
        return _ok(browser_bridge.fill(handle=args["handle"], field=args.get("field") or "password",
                                       task_id=kw.get("task_id") or "default"))
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


SCHEMAS["secret_fill"] = {
    "name": "secret_fill",
    "description": ("Log in with Monsieur's Bitwarden: fills the password (field='password') or the current 2FA code "
                    "(field='totp', generated from the saved authenticator key) into the page open in the browser. "
                    "Refuses when the page is not one of the login's saved sites (anti-phishing). Values never enter the "
                    "conversation. Find the handle with secret_search (handle = 'bw:' + id). Works with every browser engine."),
    "parameters": {"type": "object", "properties": {
        "handle": {"type": "string"}, "field": {"type": "string", "enum": ["password", "totp"], "default": "password"}},
        "required": ["handle"]}}
def _secret_otp(args: dict, **kw) -> str:
    from . import browser_bridge
    try:
        return _ok(browser_bridge.fill_received_otp(hint=args.get("site"), since_minutes=float(args.get("since_minutes") or 10),
                                                    timeout=float(args.get("timeout") or 120),
                                                    task_id=kw.get("task_id") or "default"))
    except (SecretError, KeyError) as e:
        return _ok({"error": str(e)})


SCHEMAS["secret_otp"] = {
    "name": "secret_otp",
    "description": ("Log in when the site sends its one-time code by e-mail or by message (WhatsApp, Telegram, LINE… via "
                    "Beeper) instead of an authenticator app: waits for that code (only messages received in the last "
                    "minutes that mention the site), then fills it into the code field of the page open in the browser. "
                    "Refuses when the page is not that site (anti-phishing). The code never enters the conversation. "
                    "Real SMS are not available (no SMS account in Beeper): if nothing arrives, ask Monsieur."),
    "parameters": {"type": "object", "properties": {
        "site": {"type": "string", "description": "who sends the code: site name or domain (default: the page's site)"},
        "since_minutes": {"type": "number", "default": 10, "description": "how far back to look (the code was requested this long ago at most)"},
        "timeout": {"type": "number", "default": 120, "description": "seconds to wait for the code to arrive"}}}}
HANDLERS = {"secret_search": _secret_search, "secret_fill": _secret_fill, "secret_file": _secret_file, "secret_reveal": _secret_reveal,
            "secret_create_login": _secret_create_login, "secret_capture_totp": _secret_capture_totp,
            "secret_otp": _secret_otp}


def register(ctx: Any) -> None:
    cleanup_files()
    for name, schema in SCHEMAS.items():
        try:
            ctx.register_tool(name=name, toolset="walter-secrets", schema=schema, handler=HANDLERS[name],
                              description=schema["description"], emoji="🔐")
        except Exception as e:
            logger.error("WALTER_SECRETS_DEGRADED register_tool %s: %s", name, e)
    for hook, fn in (("pre_tool_call", _pre_tool_call), ("transform_tool_result", _transform_tool_result),
                     ("transform_terminal_output", _transform_terminal_output)):
        try:
            ctx.register_hook(hook, fn)
        except Exception as e:
            logger.error("WALTER_SECRETS_DEGRADED register_hook %s: %s", hook, e)
