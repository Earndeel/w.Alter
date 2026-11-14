"""The single configuration of walter-skills (config/walter-skills.toml), loaded once, read-only."""
from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "config" / "walter-skills.toml"


@lru_cache(maxsize=1)
def load() -> dict:
    return tomllib.loads(FILE.read_text())


def get(section: str) -> dict:
    return dict(load().get(section, {}))


def poste(name: str) -> list[dict]:
    return list(load().get("postes", {}).get(name, {}).get("routes", []))
