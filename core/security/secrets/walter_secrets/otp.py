"""otp — one-time codes the owner receives by e-mail or by message (Beeper), for W.Alter's logins.

Decision 2026-10-17: when a site sends its code by e-mail or SMS-like message instead of an authenticator
app, W.Alter fetches it and fills it, like the iPhone does. Read-only, narrow by design:
  - only messages received AFTER `since` (default: the last 10 minutes), never older mail or chats;
  - only messages that mention the expected site (`hint`: its name or domain) in sender, subject or text;
  - the code is returned to the caller (filled into the page / printed for a terminal placeholder) and registered for
    masking; the audit log keeps channel + sender + time, never the code or the message text.
Sources: Gmail (gmail.readonly token of Walter Memory, connectors/google_api.py) and the Beeper Client API on the Mac
(WhatsApp, Telegram, LINE, Messenger, Instagram… — Beeper has no SMS account on 2026-10-17, so real SMS are not seen).
"""
from __future__ import annotations

import base64
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .vault import SecretError

from . import settings
BEEPER_API = settings.setting("otp", "beeper_api", "http://127.0.0.1:23373")
KEYWORDS = re.compile(r"code|otp|pin|passcode|password|mot de passe|v[ée]rification|verify|confirm|s[ée]curit[ée]|"
                      r"security|login|connexion|sign[- ]?in|authenticat|รหัส|ยืนยัน|验证码|コード", re.I)
CANDIDATE = re.compile(r"(?<![\w/.-])(?:[A-Z]{1,3}-)?(\d{3}[ -]?\d{3}|\d{4,8})(?![\w/-]|[.,]\d)")


def extract(text: str) -> str | None:
    """The one-time code in a message, or None. Needs a code keyword; prefers 6 digits; skips years and long numbers."""
    if not text or not KEYWORDS.search(text):
        return None
    found = []
    for m in CANDIDATE.finditer(text):
        code = re.sub(r"[ -]", "", m.group(1))
        if not code.isdigit() or not 4 <= len(code) <= 8:
            continue
        if len(code) == 4 and 1990 <= int(code) <= 2100:          # a year, not a code
            continue
        if len(code) == 8 and re.match(r"(19|20)\d\d(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$", code):   # a date / order number
            continue
        window = text[max(0, m.start() - 80):m.end() + 80]
        if not KEYWORDS.search(window):                            # the code must sit next to a code keyword
            continue
        found.append(code)
    if not found:
        return None
    six = [c for c in found if len(c) == 6]
    return (six or found)[0]


def _terms(hint: str) -> list[str]:
    """'https://accounts.google.com' → ['google'] ; 'GitHub' → ['github'] ; 'kie.ai' → ['kie']."""
    h = hint.lower().strip()
    if "://" in h:
        h = urllib.parse.urlparse(h).hostname or h
    parts = [p for p in re.split(r"[^a-z0-9]+", h) if p]
    stop = {"www", "com", "fr", "net", "org", "io", "ai", "co", "app", "accounts", "account", "login", "auth", "id",
            "secure", "th", "uk", "de", "https", "http", "mail", "noreply", "no", "reply"}
    keep = [p for p in parts if p not in stop and len(p) > 1]
    return keep or parts


def _matches(terms: list[str], *texts: str) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(t in blob for t in terms)


# ── e-mail ─────────────────────────────────────────────────────────────────────
def _gmail():
    from walter_memory.google import Google   # Walter Memory public client, via the shared runtime
    return Google()


def _body(payload: dict) -> str:
    out = []

    def walk(p):
        mt, data = p.get("mimeType", ""), (p.get("body") or {}).get("data")
        if data and mt in ("text/plain", "text/html"):
            t = base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
            if mt == "text/html":
                t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(style|script).*?</\1>", " ", t)))
            out.append(t)
        for c in p.get("parts") or []:
            walk(c)
    walk(payload)
    return re.sub(r"\s+", " ", " ".join(out))[:20000]


def from_email(terms: list[str], since: datetime, g=None) -> list[dict]:
    g = g or _gmail()
    base = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    q = f"after:{int(since.timestamp())} -in:sent"
    found = []
    for m in (g.get(base, q=q, maxResults=15).get("messages") or []):
        msg = g.get(f"{base}/{m['id']}", format="full")
        at = datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000, timezone.utc)
        if at < since:
            continue
        hdr = {h["name"].lower(): h["value"] for h in (msg.get("payload") or {}).get("headers") or []}
        sender, subject = hdr.get("from", ""), hdr.get("subject", "")
        body = _body(msg.get("payload") or {})
        if not _matches(terms, sender, subject, body[:3000]):
            continue
        code = extract(f"{subject} {msg.get('snippet', '')}") or extract(body)
        if code:
            found.append({"code": code, "channel": "email", "sender": sender[:120], "at": at})
    return found


# ── messages (Beeper) ──────────────────────────────────────────────────────────
def _beeper_get(path: str, token: str, **params) -> dict:
    url = BEEPER_API + path + ("?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}) if params else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}), timeout=20) as r:
        return json.load(r)


def from_messages(terms: list[str], since: datetime, token: str | None = None) -> list[dict]:
    if not token:
        from . import grants
        token = grants.access("beeper")   # the owner's Beeper, through Walter's grant
    found = []
    d = _beeper_get("/v1/chats", token, limit=40)
    for chat in d.get("items") or []:
        last = chat.get("lastActivity") or chat.get("timestamp")
        if last and datetime.fromisoformat(last.replace("Z", "+00:00")) < since:
            continue
        page = _beeper_get(f"/v1/chats/{urllib.parse.quote(chat['id'], safe='')}/messages", token)
        for m in page.get("items") or []:
            if m.get("isSender"):
                continue
            at = datetime.fromisoformat(str(m.get("timestamp", "1970-01-01T00:00:00Z")).replace("Z", "+00:00"))
            if at < since:
                continue
            text = m.get("text") or ""
            if not _matches(terms, m.get("senderName", ""), chat.get("title", ""), text):
                continue
            code = extract(text)
            if code:
                found.append({"code": code, "channel": f"message:{chat.get('accountID', '?')}",
                              "sender": (m.get("senderName") or chat.get("title") or "")[:120], "at": at})
    return found


# ── wait ───────────────────────────────────────────────────────────────────────
def wait(hint: str, *, since_minutes: float = 10, timeout: float = 120, poll: float = 6,
         channels: tuple[str, ...] = ("email", "message")) -> dict:
    """Newest code from the expected site received since `since_minutes` ago; waits up to `timeout` s for it."""
    terms = _terms(hint)
    if not terms:
        raise SecretError("hint must name the site (name or domain) that sends the code")
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    deadline, errors = time.time() + timeout, {}
    g = None
    while True:
        found = []
        if "email" in channels:
            try:
                g = g or _gmail()
                found += from_email(terms, since, g)
            except Exception as e:  # noqa: BLE001 — one source down must not block the other
                errors["email"] = type(e).__name__
        if "message" in channels:
            try:
                found += from_messages(terms, since)
            except Exception as e:  # noqa: BLE001
                errors["message"] = type(e).__name__
        if found:
            best = max(found, key=lambda f: f["at"])
            return {**best, "at": best["at"].isoformat(timespec="seconds"), "terms": terms}
        if time.time() >= deadline:
            raise SecretError(f"no code from {terms} received since {since:%H:%M} UTC"
                              + (f" (sources failing: {errors})" if errors else ""))
        time.sleep(poll)
