"""Live /models of OpenAI-compatible providers configured in Hermes (config/providers.json)."""
from __future__ import annotations

import json
from datetime import datetime
from urllib.request import Request, urlopen

from walter_router import paths
from walter_router.instance import env_value
from walter_router.research.web import MAX_BYTES, now

PROVIDERS_CONFIG = paths.CONFIG / "providers.json"


def source_hermes_providers() -> tuple[dict, datetime, str]:
    """Live /models catalogue of OpenAI-compatible providers configured in Hermes (config/providers.json)."""
    out, errors = [], {}
    for p in json.loads(PROVIDERS_CONFIG.read_text())["providers"]:
        key = env_value(p["key_env"])
        if not key:
            errors[p["provider"]] = f'{p["key_env"]} missing'
            continue
        req = Request(p["api"].rstrip("/") + "/models",
                      headers={"Authorization": f"Bearer {key}", "User-Agent": "Walter-Router/1.0",
                               "Accept": "application/json"})
        try:
            with urlopen(req, timeout=60) as resp:  # noqa: S310 (configured https endpoint)
                data = json.loads(resp.read(MAX_BYTES))["data"]
            out.append({**{k: p[k] for k in ("provider", "name", "api", "hermes_provider")}, "models": data})
        except Exception as exc:  # noqa: BLE001
            errors[p["provider"]] = f"{type(exc).__name__}: {exc}"[:200]
    if not out:
        raise ValueError(f"hermes_providers: no catalogue ({errors})")
    return {"providers": out, "errors": errors}, now(), str(PROVIDERS_CONFIG)
