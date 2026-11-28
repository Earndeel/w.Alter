"""BridgeBench leaderboard (behind Cloudflare: FlareSolverr)."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from urllib.request import Request, urlopen

from walter_router.research.web import FLARESOLVERR, MAX_BYTES, _json_object, now

BRIDGEBENCH_URL = "https://www.bridgebench.ai/leaderboard"


def bridgebench_rows(page: str) -> list[dict]:
    """Model rows of the BridgeBench leaderboard page: {id, name, vendor, provisional, scores{overall, reasoning,
    frontend, backend, oneShot, security, trustworthiness, efficiency, speed, cost}, price, blended, context}."""
    text = html.unescape(page).replace('\\"', '"')
    rows: dict[str, dict] = {}
    for m in re.finditer(r'\{"id":"[^"]+","href":"/leaderboard/', text):
        try:
            obj = json.loads(_json_object(text, m.start()))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj.get("scores"), dict):
            obj.pop("mark", None)
            rows[obj["id"]] = obj
    return list(rows.values())


def source_bridgebench() -> tuple[dict, datetime, str]:
    """BridgeBench sits behind a Cloudflare challenge: fetched through the local FlareSolverr."""
    body = json.dumps({"cmd": "request.get", "url": BRIDGEBENCH_URL, "maxTimeout": 90000}).encode()
    req = Request(FLARESOLVERR, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=150) as resp:  # noqa: S310 (local service)
        sol = json.loads(resp.read(MAX_BYTES))["solution"]
    if sol.get("status") != 200:
        raise ValueError(f"bridgebench: HTTP {sol.get('status')}")
    rows = bridgebench_rows(sol["response"])
    if len(rows) < 10:
        raise ValueError(f"bridgebench: only {len(rows)} rows parsed")
    return {"rows": rows}, now(), BRIDGEBENCH_URL
