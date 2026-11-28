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
                  "answer_within_s": (int, float), "answer_margin_s": (int, float), "pack_reserve_s": (int, float),
                  "signals": str, "readings_apart": bool, "decision_sampling": str,
                  "readings_samples": int}
PACK_KEYS = {"budget": dict, "cut_order": list, "people_tokens": int, "min_block_tokens": int, "board_tokens": int, "board_max_lines": int,
             "board_recent_hours": (int, float), "board_states": list, "subject_tokens": int,
             "horizon_max_age_s": dict, "recent_exchanges": int, "unsure_plan": (int, float), "tasks_tokens": int,
             "tasks_others": int, "experience_tokens": int, "experience_items": int,
             "experience_recent_days": (int, float), "gateway_timeout_s": (int, float), "memory_budget": dict,
             "records_budget": dict, "state_budget": dict, "workers": int, "late_grace_s": (int, float),
             "readings_wait_s": (int, float)}


def _section(name: str, keys: dict, path: str | Path | None) -> dict:
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text()).get(name)
    if not isinstance(raw, dict):
        raise ValueError(f"[{name}] missing from the walter-context configuration")
    missing = sorted(set(keys) - raw.keys())
    if missing:
        raise ValueError(f"[{name}]: missing {missing}")
    for k, t in keys.items():
        if t is bool:                               # a switch: true or false, nothing else
            if not isinstance(raw[k], bool):
                raise ValueError(f"[{name}].{k}: invalid value")
            continue
        if not isinstance(raw[k], t) or isinstance(raw[k], bool) or (isinstance(raw[k], (int, float)) and raw[k] < 0):
            raise ValueError(f"[{name}].{k}: invalid value")
    return {k: raw[k] for k in keys}


def preflight_settings(path: str | Path | None = None) -> dict:
    """[preflight]: decision samples, timeouts, windows, the degraded plan's thresholds, where the questions come from."""
    out = _section("preflight", PREFLIGHT_KEYS, path)
    if out["signals"] not in ("registry", "questions"):
        raise ValueError('[preflight].signals: "registry" or "questions"')
    if out["decision_sampling"] not in ("mean", "first"):
        raise ValueError('[preflight].decision_sampling: "mean" or "first"')
    if out["readings_samples"] < 1:
        raise ValueError("[preflight].readings_samples: 1 or more")
    return out


def pack_settings(path: str | Path | None = None) -> dict:
    """[pack]: total budget per context level, cut order, per-block budgets and the board/tasks/experience bounds."""
    out = _section("pack", PACK_KEYS, path)
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text()).get("pack") or {}
    # optional (27/11): absent = no chronological reading, the early rerank waits 8 s for the plan at most
    hours = raw.get("chronological_hours") or {}
    if not isinstance(hours, dict) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                                              for v in hours.values()):
        raise ValueError("[pack].chronological_hours: positive hours per horizon")
    out["chronological_hours"] = dict(hours)
    levels = raw.get("chronological_levels", ["L0"])
    if not isinstance(levels, list) or not set(levels) <= {"L0", "L1", "L2", "L3", "L4"}:
        raise ValueError("[pack].chronological_levels: context levels")
    out["chronological_levels"] = list(levels)
    gate = raw.get("prefetch_gate_s", 8)
    if not isinstance(gate, (int, float)) or isinstance(gate, bool) or gate < 0:
        raise ValueError("[pack].prefetch_gate_s: invalid value")
    out["prefetch_gate_s"] = gate
    if set(out["budget"]) != {"L0", "L1", "L2", "L3", "L4"} or not all(
            isinstance(v, int) and v > 0 for v in out["budget"].values()):
        raise ValueError("[pack].budget: a positive token budget for each of L0..L4")
    return out


# --- optional sections: absent from an older file = the defaults below (the behaviour before they existed) --------
LONGTEXT_DEFAULTS = {"enabled": True, "inline_chars": 1500, "head_chars": 500, "tail_chars": 600,
                     "signal_chars": 1200, "signal_sentence_chars": 280}
STATE_DEFAULTS = {"decision_state": False,        # preflight facts + plan summary built from the DecisionState
                  "living_state": False,          # the preflight reads the session's WorkingState into the DecisionState
                  "memory_refresh": False,        # memory.changed re-projects Memory's working state (lib call, background)
                  "coalesce_ms": 150, "max_items": 120, "text_chars": 2500, "observation_ttl_s": 1800,
                  "memory_ttl_s": 3600, "tool_ttl_s": 900, "max_sessions": 200, "idle_evict_s": 86400,
                  "reassess_cache": 256, "reassess_timeout_s": 6.0}


MEDIA_DEFAULTS = {"enabled": True,                # images / voice notes of a message read by the decision model itself
                  "audio": True,                  # … voice notes too (beside their transcript)
                  "image_max_bytes": 3_000_000, "audio_max_bytes": 2_000_000,   # Liquid's body limit is 4.5 MB
                  "roots": ["@instance/state/core/telegram", "@instance/state/context/bench"]}


def _optional(name: str, defaults: dict, path: str | Path | None) -> dict:
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text()).get(name) or {}
    out = dict(defaults)
    for k, v in raw.items():
        if k not in defaults:
            raise ValueError(f"[{name}].{k}: unknown key")
        d = defaults[k]
        ok = isinstance(v, bool) if isinstance(d, bool) else \
            (isinstance(v, list) and all(isinstance(x, str) and x for x in v)) if isinstance(d, list) else \
            (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0)
        if not ok:
            raise ValueError(f"[{name}].{k}: invalid value")
        out[k] = v
    return out


def longtext_settings(path: str | Path | None = None) -> dict:
    """[longtext]: how a long owner message is represented for the decision model (never cut at its end)."""
    return _optional("longtext", LONGTEXT_DEFAULTS, path)


def state_settings(path: str | Path | None = None) -> dict:
    """[state]: the living WorkingState and the DecisionState; the two preflight switches default to off."""
    return _optional("state", STATE_DEFAULTS, path)


DIGEST_DEFAULTS = {"enabled": False, "max_tokens": 250, "timeout_ms": 300}


def digest_settings(path: str | Path | None = None) -> dict:
    """[digest] (19/11): the situation digest the preflight adds to its single Decision call (walter_memory.digest)."""
    return _optional("digest", DIGEST_DEFAULTS, path)


def media_settings(path: str | Path | None = None) -> dict:
    """[media] (18/11): the images and voice notes of a message read by the preflight's decision model."""
    return _optional("media", MEDIA_DEFAULTS, path)


# Lot 1 of the payload plan (owner 2026-11-23). Absent sections = the behaviour before (rollback = false / the old list).
ANCHORS_DEFAULTS = {"hint": False,                # true: a name Walter Memory knows is a hint the decision model reads
                                                  # (state `names_known_to_memory`), never a trigger of memory
                    "assistant_names": ["walter", "w.alter", "w-alter", "walt"]}   # never a hint (« salut walter »)
DEDUPE_DEFAULTS = {"memory_header": False,        # true: Memory's own preamble is not repeated under the pack's header
                   "native_history": ["claude_code", "codex", "dsh"]}   # runtimes that show their history themselves


def anchors_settings(path: str | Path | None = None) -> dict:
    """[anchors] (payload lot 1, 23/11): what a name Walter Memory knows does to the plan."""
    return _optional("anchors", ANCHORS_DEFAULTS, path)


def dedupe_settings(path: str | Path | None = None) -> dict:
    """[dedupe] (payload lot 1, 23/11): what the pack does not say twice."""
    return _optional("dedupe", DEDUPE_DEFAULTS, path)


# P1 (owner 2026-11-26, after the benches of 25–26/11): an attachment Decision is unsure of brings none of the thread's
# blocks. Defaults = the behaviour before (no runtime): every chosen thread brings its blocks.
THREAD_BLOCKS_DEFAULTS = {"runtimes": [], "min_confidence": 0.0}


def thread_blocks_settings(path: str | Path | None = None) -> dict:
    """[thread_blocks]: for these runtimes, a thread chosen with less confidence brings no thread blocks."""
    out = _optional("thread_blocks", THREAD_BLOCKS_DEFAULTS, path)
    if out["min_confidence"] > 1:
        raise ValueError("[thread_blocks].min_confidence: between 0 and 1")
    return out
