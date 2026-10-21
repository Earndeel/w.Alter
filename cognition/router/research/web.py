"""Web access shared by every source: JSON / pages, FlareSolverr behind Cloudflare challenges, Next.js flight data."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from walter_router.instance import env_value

MAX_BYTES = 64 * 1024 * 1024


FLARESOLVERR = os.environ.get("WALTER_FLARESOLVERR", "http://127.0.0.1:8191/v1")  # local, behind Cloudflare sites


def now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_json(url: str, payload: dict | None = None) -> Any:
    headers = {"User-Agent": "Walter-Router/1.0", "Accept": "application/json"}
    data = None
    if payload is not None:
        headers.update({"Content-Type": "application/json", "Origin": "https://kie.ai", "Referer": "https://kie.ai/pricing"})
        data = json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=headers), timeout=60) as resp:  # noqa: S310 (fixed https URLs)
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response too large: {url}")
    return json.loads(raw)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return now()
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch_text(url: str) -> str:
    """A page, directly; through the local FlareSolverr when the site answers 403/503 (Cloudflare challenge —
    Arena since 2026-10-14)."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Walter-Router/1.0)", "Accept": "text/html"})
    try:
        with urlopen(req, timeout=40) as resp:  # noqa: S310 (fixed https host)
            raw = resp.read(MAX_BYTES + 1)
        return raw.decode("utf-8", "replace")
    except HTTPError as exc:
        if exc.code not in (403, 503):
            raise
    body = json.dumps({"cmd": "request.get", "url": url, "maxTimeout": 90000}).encode()
    with urlopen(Request(FLARESOLVERR, data=body, headers={"Content-Type": "application/json"}), timeout=150) as resp:  # noqa: S310
        sol = json.loads(resp.read(MAX_BYTES))["solution"]
    if sol.get("status") != 200:
        raise ValueError(f"{url}: HTTP {sol.get('status')} through FlareSolverr")
    return sol["response"]


def _json_array(text: str, start: int) -> list:
    """The JSON array starting at text[start] == '[' (string-aware bracket matching)."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:k + 1])
    raise ValueError("unterminated array")


def _json_object(text: str, start: int) -> str:
    """The JSON object starting at text[start] == '{' (string-aware brace matching)."""
    depth, in_str, esc = 0, False, False
    for k in range(start, len(text)):
        ch = text[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:k + 1]
    raise ValueError("unterminated object")


def rsc_text(page: str) -> str:
    """Concatenated Next.js flight payload (self.__next_f.push([1, "..."])) of a server-rendered page."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def _github_json(url: str) -> Any:
    headers = {"User-Agent": "Walter-Router/1.0", "Accept": "application/vnd.github+json"}
    token = env_value("GITHUB_TOKEN")
    if token:   # optional: lifts the 60 calls/h anonymous limit (header only, never logged)
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=60) as resp:  # noqa: S310 (fixed https host)
        return json.loads(resp.read(MAX_BYTES))
