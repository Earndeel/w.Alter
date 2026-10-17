"""Bridge between W.Alter's Bitwarden access and Hermes' native model-blind browser vault (agent/vault_backends).

Hermes already fills passwords and one-time codes from Bitwarden without the model ever seeing them
(browser_vault_list / browser_vault_fill / browser_vault_enter_code). Two gaps for an autonomous agent:
  1. the Bitwarden backend is unlocked only by a human typing the master password in a prompt — impossible from
     Telegram/cron. `ensure_unlocked()` hands it the session minted by ~/.hermes/bin/bw-unlock instead;
  2. new accounts are saved to the local vault, not Bitwarden, and sign-up (new-password) fields are never filled.
     `create_login()` generates a strong password, saves the login in Bitwarden FIRST, then fills the sign-up form;
     `capture_totp()` stores the site's authenticator key (otpauth URI or shown secret) in that login, so
     browser_vault_enter_code mints every later code itself.
Values travel page ⇄ Bitwarden server-side only; tool results carry handles and counts.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone

from ...vault import VAULT, SecretError, audit

FOLDER = "W.Alter – Comptes créés"
BASE32 = re.compile(r"^[A-Z2-7]{16,64}=*$")
# Firefox/Camoufox does not expose autocomplete=one-time-code and Hermes' classifier matches English labels only.
OTP_WORDS = re.compile(r"(?i)(otp|2fa|mfa|totp|one.?time|verif|vérif|code|chiffres|digits|authenticat|authentif|security|sécurité|token|pin)")


def _otp_controls(controls: list) -> list:
    from agent.vault_login_classifier import ClassifiedLoginControl, classify_otp_controls
    found = classify_otp_controls(controls)
    if found:
        return found
    return [ClassifiedLoginControl(c, 60, "one-time-code") for c in controls
            if c.type in ("text", "tel", "number", "")
            and (OTP_WORDS.search(f"{c.name} {c.label}") or (c.max_length or 0) in range(4, 9))
            and not re.search(r"(?i)mail|user|login|identifiant|search|recherche", f"{c.name} {c.label}")]

_FIND_TOTP_JS = r"""(() => {
  const out = new Set();
  const add = (s) => { if (s && typeof s === "string") out.add(s); };
  document.querySelectorAll("a[href], [data-uri], [data-otpauth], img[alt], img[src], input, textarea, code, pre, kbd, samp, span, div, p, td, strong")
    .forEach((el) => {
      add(el.getAttribute && el.getAttribute("href")); add(el.getAttribute && el.getAttribute("data-uri"));
      add(el.getAttribute && el.getAttribute("data-otpauth")); add(el.getAttribute && el.getAttribute("alt"));
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") add(el.value);
      if (el.children.length === 0) add(el.textContent);
    });
  return JSON.stringify(Array.from(out).filter((s) => s.length < 600).filter((s) =>
    /otpauth:\/\//i.test(s) || /^[A-Z2-7 ]{16,80}=*$/.test(s.trim().toUpperCase())));
})()"""


def ensure_unlocked() -> bool:
    """Give Hermes' Bitwarden backend the bw-unlock session (no human prompt)."""
    from agent.vault_backends import unlock as U
    if U.is_unlocked("bitwarden"):
        return True
    token = VAULT._session()
    return U.store_session_token("bitwarden", token, U.begin_unlock("bitwarden"))


def _bw_stdin(*args: str, data: str) -> str:
    import os
    env = {**os.environ, "BW_SESSION": VAULT._session(), "BW_NOINTERACTION": "true"}
    r = subprocess.run(["bw", *args, "--nointeraction"], input=data, capture_output=True, text=True, timeout=120, env=env)
    if r.returncode:
        raise SecretError(f"bw {args[0]} failed (diagnostic suppressed)")
    return r.stdout


def _enc(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj).encode()).decode()


def _folder_id() -> str:
    for f in json.loads(VAULT._bw("list", "folders")):
        if f["name"] == FOLDER:
            return f["id"]
    return json.loads(_bw_stdin("create", "folder", data=_enc({"name": FOLDER})))["id"]


# ── page access: Chromium (supervisor CDP, Hermes native) or Camofox (W.Alter's default browser) ──────────────
def _camofox_session(task_id: str) -> dict | None:
    try:
        from tools import browser_camofox as bc
    except ImportError:
        return None
    if not bc.is_camofox_mode():
        return None
    s = bc._sessions.get(task_id)
    return s if s and s.get("tab_id") else None


def _eval(task_id: str, expression: str, secret: bool = False) -> dict:
    """Evaluate JS in the agent's current page. Secret-bearing expressions go to Camofox in a local HTTP body
    (127.0.0.1, never argv) or over the CDP supervisor socket — never through the agent-browser CLI."""
    s = _camofox_session(task_id)
    if s:
        from tools import browser_camofox as bc
        try:
            d = bc._post("/tab/evaluate", {"userId": s["user_id"], "tabId": s["tab_id"], "expression": expression}, timeout=30)
            return {"success": bool(d.get("ok")), "result": d.get("result")}
        except Exception as e:
            return {"success": False, "error": f"camofox evaluate: {type(e).__name__}"}
    from tools.browser_vault_tool import _eval_js, _eval_js_secret
    return _eval_js_secret(task_id, expression) if secret else _eval_js(task_id, expression)


def _parsed(res: dict):
    from tools.browser_vault_tool import _parse_json_result
    out = _parse_json_result(res.get("result")) if res.get("success") else None
    return _parse_json_result(out) if isinstance(out, str) else out


def _page_origin(task_id: str) -> str | None:
    from agent.vault_store import normalize_origin
    href = str(_parsed(_eval(task_id, "window.location.href")) or "").strip().strip('"')
    try:
        return normalize_origin(href) if href and href != "about:blank" else None
    except Exception:
        return None


def _controls(task_id: str) -> tuple[str, list]:
    from agent.vault_login_classifier import LoginControl, build_inspection_js
    nonce = secrets.token_hex(8)
    raw = _parsed(_eval(task_id, build_inspection_js(nonce)))
    return nonce, [LoginControl.from_dict(r) for r in (raw or []) if isinstance(r, dict)]


def _write(task_id: str, fills: list, origin: str, nonce: str) -> int:
    from agent.vault_login_classifier import build_fill_js
    out = _parsed(_eval(task_id, build_fill_js(fills, expected_origin=origin, nonce=nonce), secret=True))
    if isinstance(out, dict) and out.get("refused"):
        raise SecretError("the page navigated before the fill — nothing was written")
    return int(out.get("filled", 0)) if isinstance(out, dict) else 0


def _fill_password_fields(task_id: str, origin: str, password: str) -> int:
    """Sign-up: fill every visible password input (password + confirmation)."""
    from agent.redact import register_vault_redaction_value
    nonce, controls = _controls(task_id)
    targets = [c for c in controls if c.type == "password"]
    if not targets:
        return 0
    register_vault_redaction_value(password)
    return _write(task_id, [{"index": c.index, "token": "current-password", "value": password} for c in targets], origin, nonce)


def fill(*, handle: str, field: str = "password", task_id: str = "default") -> dict:
    """Login: fill the password (or the current one-time code) of a Bitwarden login into the current page —
    only when the page origin exactly matches one of the login's URIs (anti-phishing)."""
    from agent.redact import register_vault_redaction_value
    from agent.vault_login_classifier import (build_otp_fills, classify_login_control, classify_otp_controls,
                                              select_password_fill)
    from agent.vault_store import normalize_origin
    item = json.loads(VAULT._bw("get", "item", handle.removeprefix("bw:")))
    allowed = set()
    for u in (item.get("login") or {}).get("uris") or []:
        try:
            allowed.add(normalize_origin(u.get("uri") or ""))
        except Exception:
            pass
    origin = _page_origin(task_id)
    if not origin or origin not in allowed:
        audit("fill_refused", item, field, origin=origin)
        raise SecretError(f"page origin {origin!r} is not a saved site of this login {sorted(allowed)} — refusing "
                          "(possible phishing or wrong item)")
    nonce, controls = _controls(task_id)
    if field == "totp":
        value = VAULT._bw("get", "totp", item["id"]).strip()
        otp = _otp_controls(controls)
        if not value.isdigit() or not otp:
            raise SecretError("no authenticator key saved for this login" if not value.isdigit() else "no code field on this page")
        fills = build_otp_fills(otp, value)
    else:
        value = (item.get("login") or {}).get("password") or ""
        fills = select_password_fill([x for x in (classify_login_control(c) for c in controls) if x], value)
        if not fills:
            raise SecretError("no password field on this page")
    register_vault_redaction_value(value)
    n = _write(task_id, fills, origin, nonce)
    del value
    audit("fill", item, field, origin=origin)
    return {"success": n > 0, "filled_fields": n, "origin": origin, "field": field,
            "next": "Submit the form." if field == "totp" else "Type the username yourself if needed, then submit."}


def create_login(*, username: str, url: str | None = None, label: str | None = None, length: int = 24,
                 symbols: bool = True, fill: bool = True, task_id: str = "default") -> dict:
    from agent.vault_store import normalize_origin
    origin = normalize_origin(url) if url else _page_origin(task_id)
    if not origin:
        raise SecretError("open the sign-up page first (or pass url)")
    host = origin.split("://", 1)[-1]
    flags = "-ulns" if symbols else "-uln"
    password = VAULT._bw("generate", flags, "--length", str(max(12, min(int(length), 64)))).strip()
    item = {"type": 1, "name": label or host, "folderId": _folder_id(),
            "notes": f"Compte créé par W.Alter le {datetime.now(timezone.utc):%Y-%m-%d} (mot de passe généré, jamais vu par le modèle).",
            "login": {"username": username, "password": password, "uris": [{"uri": origin, "match": None}]}}
    created = json.loads(_bw_stdin("create", "item", data=_enc(item)))      # saved BEFORE the form is submitted
    VAULT._listed = 0                                                         # refresh caches
    audit("create_login", created, "password", origin=origin)
    filled = _fill_password_fields(task_id, origin, password) if fill else 0
    del password
    return {"handle": f"bw:{created['id']}", "item": created["name"], "origin": origin, "username": username,
            "filled_password_fields": filled,
            "next": ("Type the username/e-mail yourself (browser_type), then submit. Later logins: "
                     "secret_fill(handle). If the site offers 2FA by authenticator app, show its key and call "
                     "secret_capture_totp(handle).")}


def capture_totp(*, handle: str, task_id: str = "default") -> dict:
    """Read the authenticator key the CURRENT page shows and store it in the Bitwarden login."""
    from agent.redact import register_vault_redaction_value
    item_id = handle.removeprefix("bw:")
    item = json.loads(VAULT._bw("get", "item", item_id))
    origin = _page_origin(task_id)
    cands = _parsed(_eval(task_id, _FIND_TOTP_JS)) or []
    uri = next((urllib.parse.unquote(c.strip()) for c in cands if "otpauth://" in c.lower()), None)
    if uri:
        uri = uri[uri.lower().find("otpauth://"):]
        secret = (urllib.parse.parse_qs(urllib.parse.urlparse(uri).query).get("secret") or [""])[0]
    else:
        secret = next((c.replace(" ", "").upper() for c in cands if BASE32.match(c.replace(" ", "").upper())), "")
        if secret:
            issuer = (origin or "").split("://", 1)[-1]
            user = (item.get("login") or {}).get("username") or ""
            uri = f"otpauth://totp/{urllib.parse.quote(issuer)}:{urllib.parse.quote(user)}?secret={secret}&issuer={urllib.parse.quote(issuer)}"
    if not secret:
        raise SecretError("no authenticator key on this page — click the site's 'can't scan the QR code? / show key' link "
                          "first (QR images are not decoded)")
    register_vault_redaction_value(secret)
    register_vault_redaction_value(uri)
    item.setdefault("login", {})["totp"] = uri
    _bw_stdin("edit", "item", item_id, data=_enc(item))
    del secret, uri
    code = VAULT._bw("get", "totp", item_id).strip()                       # proves the seed is usable
    audit("capture_totp", item, "totp", origin=origin)
    return {"saved": True, "handle": handle, "codes_work": code.isdigit(),
            "next": "Call secret_fill(handle, field='totp') to type the current code and confirm the 2FA setup."}


def fill_received_otp(*, hint: str | None = None, since_minutes: float = 10, timeout: float = 120,
                      task_id: str = "default") -> dict:
    """Login: wait for the one-time code the site sent by e-mail or message (otp.py) and fill it into the page.
    The page must belong to the site named by `hint` (anti-phishing: a code is never typed into another site)."""
    from ... import otp
    from agent.redact import register_vault_redaction_value
    origin = _page_origin(task_id)
    if not origin:
        raise SecretError("open the page that asks for the code first")
    page_terms = otp._terms(origin)
    terms = otp._terms(hint) if hint else page_terms
    if not set(terms) & set(page_terms):
        audit("otp_refused", None, "otp", origin=origin, hint=hint)
        raise SecretError(f"the page {origin!r} is not the site {terms} — refusing to fill its code here")
    nonce, controls = _controls(task_id)
    fields = _otp_controls(controls)
    if not fields:
        raise SecretError("no code field on this page")
    got = otp.wait(hint or origin, since_minutes=since_minutes, timeout=timeout)
    from agent.vault_login_classifier import build_otp_fills
    code = got.pop("code")
    register_vault_redaction_value(code)
    nonce, controls = _controls(task_id)                     # the page may have re-rendered while we waited
    n = _write(task_id, build_otp_fills(_otp_controls(controls), code), origin, nonce)
    del code
    audit("otp_fill", None, "otp", origin=origin, channel=got["channel"], sender=got["sender"], received_at=got["at"])
    return {"success": n > 0, "filled_fields": n, "origin": origin, "channel": got["channel"], "sender": got["sender"],
            "received_at": got["at"], "next": "Submit the form."}
