"""The owner's ChatGPT/Codex account read with W.Alter's OWN Codex session (2026-11-10: no longer through Hermes).

Two read-only calls of the ChatGPT backend, authenticated by the walter-secrets grant `codex-subscription` (the session
walter-llm's Codex routes use; the token is read once per process, never printed nor put in a URL):
  catalog()  the models the account may run (`/backend-api/codex/models`)
  usage()    its live quota windows (`/backend-api/wham/usage`)
"""
from __future__ import annotations

import base64
import json
import subprocess
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = "https://chatgpt.com/backend-api"
GRANT = "codex-subscription"
# The models endpoint reads client_version as a Codex CLI compatibility version and hides models newer than it:
# the newest first, then the ungated sentinel.
CLIENT_VERSIONS = ("99.0.0", "0.0.0")
WINDOW_BY_SECONDS = {18000: "session", 604800: "weekly"}
WINDOW_BY_POSITION = (("primary_window", "session"), ("secondary_window", "weekly"))

_TOKEN: list[str] = []


def _token() -> str:
    if not _TOKEN:
        r = subprocess.run(["walter-secret", "grant", "access", GRANT], capture_output=True, text=True, timeout=120)
        if r.returncode or not r.stdout.strip():
            raise ValueError(f"codex: grant {GRANT} unavailable")
        _TOKEN.append(r.stdout.strip())
    return _TOKEN[0]


def headers(token: str) -> dict:
    """Bearer + the workspace headers the backend derives from the OAuth JWT (account id, data residency)."""
    out = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "codex-cli"}
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("https://api.openai.com/auth", {})
    except (IndexError, ValueError):
        return out
    if claims.get("chatgpt_account_id"):
        out["ChatGPT-Account-ID"] = claims["chatgpt_account_id"]
    residency = claims.get("chatgpt_data_residency") or claims.get("chatgpt_compute_residency")
    if isinstance(residency, str) and residency.strip():
        out["x-openai-internal-codex-residency"] = residency.strip()
    return out


def _get(path: str, timeout: int = 30) -> dict:
    with urlopen(Request(BASE + path, headers=headers(_token())), timeout=timeout) as r:  # noqa: S310 (fixed host)
        return json.loads(r.read() or b"{}")


def ranked(entries: list) -> list[str]:
    """Visible slugs by (priority, slug): `visibility: hide` entries are not offered to the account."""
    out = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("slug"), str) or not e["slug"].strip():
            continue
        if str(e.get("visibility") or "").strip().lower() in ("hide", "hidden"):
            continue
        out.append((int(e["priority"]) if isinstance(e.get("priority"), (int, float)) else 10_000, e["slug"].strip()))
    return list(dict.fromkeys(slug for _, slug in sorted(out)))


def catalog() -> list[str]:
    """Model slugs the account may run (first client version that answers a non-empty list)."""
    for v in CLIENT_VERSIONS:
        try:
            entries = _get(f"/codex/models?client_version={v}").get("models")
        except (OSError, ValueError):
            continue
        slugs = ranked(entries or [])
        if slugs:
            return slugs
    raise ValueError("codex: catalogue unavailable")


def windows(payload: dict) -> list[dict]:
    """Quota windows of a /wham/usage answer, named by their published duration (position only as fallback)."""
    rate = payload.get("rate_limit") or {}
    out = []
    for key, fallback in WINDOW_BY_POSITION:
        w = rate.get(key) or {}
        if not isinstance(w, dict) or w.get("used_percent") is None:
            continue
        secs = w.get("limit_window_seconds")
        reset = w.get("reset_at")
        if isinstance(reset, (int, float)):
            reset = datetime.fromtimestamp(reset, timezone.utc).isoformat()
        out.append({"window": WINDOW_BY_SECONDS.get(int(secs), fallback) if isinstance(secs, (int, float)) else fallback,
                    "used_percent": float(w["used_percent"]), "resets_at": reset,
                    "detail": {"plan": payload.get("plan_type")}})
    return out


def usage() -> list[dict]:
    got = windows(_get("/wham/usage"))
    if not got:
        raise ValueError("codex usage unavailable")
    return got
