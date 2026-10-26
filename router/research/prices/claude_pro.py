"""Read the subscription catalogue/quota through Walter Secrets' declared grant interface."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from walter_router import instance
from walter_router.research.web import now


def settings() -> dict:
    """Runtime bindings live in the active instance's llm gateway settings."""
    path = instance._walter("config", "llm", "gateway.json")
    return (json.loads(Path(path).read_text()).get("claude_subscription") or {}) if path else {}


def account_json(endpoint: str) -> dict:
    """Fixed read-only Anthropic account endpoints; token is never returned in diagnostics."""
    if endpoint not in {"/v1/models", "/api/oauth/usage"}:
        raise ValueError("invalid_claude_account_endpoint")
    conf = settings()
    if not conf.get("enabled"):
        raise ValueError("claude_subscription_disabled")
    token = subprocess.run(["walter-secret", "grant", "access", conf.get("grant", "claude-subscription")],
                           capture_output=True, text=True, timeout=60)
    if token.returncode or not token.stdout.strip():
        raise ValueError("claude_subscription_unavailable")
    request = Request("https://api.anthropic.com" + endpoint, headers={
        "Authorization": "Bearer " + token.stdout.strip(), "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20", "User-Agent": "walter-router"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(f"claude_account_http_{exc.code}") from None


def source_claude_pro():
    """Only instance-verified models become executable offers; catalogue presence alone is not validation."""
    conf = settings()
    if not conf.get("enabled"):
        return {"models": [], "catalogue_models": [], "enabled": False}, now(), "Anthropic subscription (disabled)"
    data = account_json("/v1/models")
    if data.get("has_more"):
        raise ValueError("claude_catalogue_pagination_requires_update")
    ids = [row["id"] for row in data.get("data", [])]
    if not ids:
        raise ValueError("claude_catalogue_empty")
    verified = set(conf.get("verified_models") or [])
    return {"models": [mid for mid in ids if mid in verified], "catalogue_models": ids}, now(), "https://api.anthropic.com/v1/models"


def read_usage() -> list[dict]:
    """Real five-hour/weekly meters, without account identifiers, credit balances or token values."""
    data = account_json("/api/oauth/usage")
    rows = []
    for key, name in (("five_hour", "session"), ("seven_day", "weekly"),
                      ("seven_day_opus", "weekly_opus"), ("seven_day_sonnet", "weekly_sonnet")):
        window = data.get(key)
        if isinstance(window, dict) and window.get("utilization") is not None:
            rows.append({"window": name, "used_percent": float(window["utilization"]),
                         "resets_at": window.get("resets_at"), "detail": {"subscription": True}})
    if not rows:
        raise ValueError("claude_usage_empty")
    return rows
