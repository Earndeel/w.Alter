"""Public lookup: which vault item and field back a local secret name (env var), from the map that
`secrets_sync build-map` keeps. Consumers (walter-llm…) ask here instead of reading the map file themselves."""
from __future__ import annotations

import json

from . import settings

MAP = settings.DATA_ROOT / "vault/secrets-map.json"


def entry(env_name: str) -> dict:
    """The map entry for `env_name`, preferring the instance's first managed env file (sync.env_files[0])."""
    entries = json.loads(MAP.read_text())["entries"]
    files = settings.setting("sync", "env_files", [])
    preferred = f"env:{files[0]}" if files else None
    named = [e for e in entries if e["target"].endswith(f":{env_name}")]
    found = next((e for e in named if preferred and e["target"].startswith(preferred)), None) or next(iter(named), None)
    if not found:
        raise LookupError(f"{env_name} is not in the vault map")
    return found
