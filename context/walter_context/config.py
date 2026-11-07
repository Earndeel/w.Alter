"""Tunables, read from config/walter-context.toml (the only place they live)."""
from __future__ import annotations

import fnmatch
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get("WALTER_CONTEXT_CONFIG", Path(__file__).resolve().parent.parent / "config" / "walter-context.toml"))


@dataclass(frozen=True)
class Projection:
    keep_turns: int
    live_keep_steps: int
    tool_keep_chars: int
    excerpt_chars: int
    args_chars: int
    text_clip_chars: int
    brief_answer_chars: int
    user_label: str
    assistant_label: str


@dataclass(frozen=True)
class Policy:
    horizon_calls: float
    min_gain_tokens: int
    compact_share: float
    record_share: float
    regret_tokens: int
    emergency_share: float


@dataclass(frozen=True)
class Profile:
    match: str
    effective_budget: int
    hard_budget: int
    cache: str
    cache_ttl_s: float
    cached_cost: float
    write_cost: float


@dataclass(frozen=True)
class Config:
    projection: Projection
    policy: Policy
    profiles: tuple[Profile, ...]

    def profile(self, model: str | None) -> Profile:
        name = (model or "").lower()
        for p in self.profiles:
            if fnmatch.fnmatchcase(name, p.match):
                return p
        return self.profiles[-1]


def _build(cls, raw: dict):
    names = {f.name for f in fields(cls)}
    missing = names - raw.keys()
    if missing:
        raise ValueError(f"{cls.__name__}: missing {sorted(missing)}")
    return cls(**{k: raw[k] for k in names})


def load(path: str | Path | None = None) -> Config:
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text())
    profiles = tuple(_build(Profile, m) for m in raw["model"])
    if not profiles or profiles[-1].match != "*":
        raise ValueError("the last [[model]] must be the default (match = \"*\")")
    return Config(_build(Projection, raw["projection"]), _build(Policy, raw["policy"]), profiles)


def capability_settings(path: str | Path | None = None) -> dict:
    """Capability-note settings stay separate from compression policy and model profiles."""
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text())
    settings = raw["capabilities"]
    if (not isinstance(settings["router_enabled"], bool)
            or not isinstance(settings["timeout_seconds"], (int,float)) or settings["timeout_seconds"] <= 0
            or not isinstance(settings["max_chars"], int) or settings["max_chars"] <= 0):
        raise ValueError("invalid capability-note settings")
    out = {k: settings[k] for k in ("router_enabled", "timeout_seconds", "max_chars")}
    # Module layer (every module's level-0 brief, composed): optional keys, defaults keep older configs valid.
    out["modules_enabled"] = settings.get("modules_enabled", True)
    out["layer_max_chars"] = settings.get("layer_max_chars", 12000)
    if (not isinstance(out["modules_enabled"], bool) or not isinstance(out["layer_max_chars"], int)
            or out["layer_max_chars"] <= 0):
        raise ValueError("invalid capability-note settings")
    return out
