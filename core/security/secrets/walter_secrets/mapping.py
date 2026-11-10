"""Public lookup: which vault item and field back a local secret name (env var), from the map that
`secrets_sync build-map` keeps. Consumers (walter-llm…) ask here instead of reading the map file themselves."""
from __future__ import annotations

import json

from . import settings

MAP = settings.DATA_ROOT / "vault/secrets-map.json"


def entry(env_name: str) -> dict:
    """The map entry for `env_name`, preferring the instance's first managed env file (sync.env_files[0]). A key that
    lives only in the vault (no env file) is declared in the instance's [keys] declared table and resolved by name."""
    entries = json.loads(MAP.read_text())["entries"]
    files = settings.setting("sync", "env_files", [])
    preferred = f"env:{files[0]}" if files else None
    named = [e for e in entries if e["target"].endswith(f":{env_name}")]
    found = next((e for e in named if preferred and e["target"].startswith(preferred)), None) or next(iter(named), None)
    if not found:
        item = (settings.setting("keys", "declared", {}) or {}).get(env_name)
        if not item:
            raise LookupError(f"{env_name} is not in the vault map")
        from .vault import VAULT   # imported here: the map alone needs no Bitwarden session
        i = VAULT.find(item)
        return {"target": f"declared:{env_name}", "item_id": i["id"], "item": i["name"], "field": "password"}
    return found
