"""Memory V1 switches (`config/organic.toml`, instance override first) — read once per process, safe defaults."""
from __future__ import annotations

import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

DEFAULTS = {"generations": {"enforce": True}}


@lru_cache(maxsize=1)
def settings() -> dict:
    path = None
    try:
        path = subprocess.run(["walter", "instance", "config", "memory", "organic.toml"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "config" / "organic.toml"
    try:
        data = tomllib.loads(p.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    return {k: {**v, **(data.get(k) or {})} for k, v in DEFAULTS.items()}


def enabled(section: str, key: str = "enforce") -> bool:
    return bool(settings().get(section, {}).get(key, False))
