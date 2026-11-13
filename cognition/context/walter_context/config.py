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


# --- preflight and per-message pack (lot C2, 2026-11-11) -----------------------------------------------------------
PREFLIGHT_KEYS = {"decision_samples": int, "decision_timeout_s": (int, float), "reply_window_s": (int, float),
                  "floor_window_s": (int, float), "router_ttl_s": (int, float), "degraded_min_similarity": (int, float),
                  "degraded_profile_max_age_s": (int, float), "previous_chars": int, "previous_timeout_s": (int, float),
                  "answer_within_s": (int, float), "answer_margin_s": (int, float), "pack_reserve_s": (int, float)}
PACK_KEYS = {"budget": dict, "cut_order": list, "min_block_tokens": int, "board_tokens": int, "board_max_lines": int,
             "board_recent_hours": (int, float), "board_states": list, "subject_tokens": int,
             "horizon_max_age_s": dict, "recent_exchanges": int, "unsure_plan": (int, float), "tasks_tokens": int,
             "tasks_others": int, "experience_tokens": int, "experience_items": int,
             "experience_recent_days": (int, float), "gateway_timeout_s": (int, float), "memory_budget": dict,
             "records_budget": dict, "state_budget": dict, "workers": int, "late_grace_s": (int, float)}


def _section(name: str, keys: dict, path: str | Path | None) -> dict:
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text()).get(name)
    if not isinstance(raw, dict):
        raise ValueError(f"[{name}] missing from the walter-context configuration")
    missing = sorted(set(keys) - raw.keys())
    if missing:
        raise ValueError(f"[{name}]: missing {missing}")
    for k, t in keys.items():
        if not isinstance(raw[k], t) or isinstance(raw[k], bool) or (isinstance(raw[k], (int, float)) and raw[k] < 0):
            raise ValueError(f"[{name}].{k}: invalid value")
    return {k: raw[k] for k in keys}


def preflight_settings(path: str | Path | None = None) -> dict:
    """[preflight]: decision samples, timeouts, windows and the degraded plan's thresholds."""
    return _section("preflight", PREFLIGHT_KEYS, path)


def pack_settings(path: str | Path | None = None) -> dict:
    """[pack]: total budget per context level, cut order, per-block budgets and the board/tasks/experience bounds."""
    out = _section("pack", PACK_KEYS, path)
    if set(out["budget"]) != {"L0", "L1", "L2", "L3", "L4"} or not all(
            isinstance(v, int) and v > 0 for v in out["budget"].values()):
        raise ValueError("[pack].budget: a positive token budget for each of L0..L4")
    return out
