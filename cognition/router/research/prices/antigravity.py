"""Google AI Pro through the official Antigravity CLI: the account's model list, as offers the instance qualified."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from walter_router import instance
from walter_router.research.web import now


def settings() -> dict:
    """Runtime bindings live in the active instance's llm gateway settings."""
    path = instance._walter("config", "llm", "gateway.json")
    return (json.loads(Path(path).read_text()).get("antigravity_subscription") or {}) if path else {}


def _path(value: str) -> str:
    return str(instance._expand(value))


def base_id(cli_id: str) -> str:
    """Offer key of a CLI id: the reasoning level is a route parameter (same rule as walter-llm's adapter)."""
    import re
    return re.sub(r"-(low|medium|high)$", "", re.sub(r"-thinking$", "", cli_id))


def source_antigravity():
    """`agy models` (the CLI's own read of the account); only instance-qualified models become executable offers."""
    conf = settings()
    if not conf.get("enabled"):
        return {"models": [], "catalogue_models": [], "enabled": False}, now(), "Antigravity CLI (disabled)"
    home = _path(conf["home"])
    out = subprocess.run([_path(conf["cli"]), "models"], capture_output=True, text=True, timeout=120, cwd=home,
                         env={"HOME": home, "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, stdin=subprocess.DEVNULL)
    ids = [line.split("\t", 1)[0].strip() for line in out.stdout.splitlines() if "\t" in line]
    if out.returncode or not ids:
        raise ValueError("antigravity_catalogue_unavailable")   # signed out, or CLI changed: never an empty catalogue
    verified = set(conf.get("verified_models") or [])
    models = sorted({base_id(i) for i in ids if i in verified})
    return {"models": models, "catalogue_models": ids,
            "efforts": {m: sorted({i.rsplit("-", 1)[1] for i in ids if i in verified and base_id(i) == m
                                   and i.rsplit("-", 1)[1] in ("low", "medium", "high")}) for m in models}}, \
        now(), "agy models (Antigravity CLI)"
