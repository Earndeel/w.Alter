"""Memory V1 switches (`config/organic.toml`, instance override first) — read once per process, safe defaults."""
from __future__ import annotations

import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

DEFAULTS = {"generations": {"enforce": True}, "extraction": {"mode": "active"}, "working_memory": {"mode": "shadow"},
            "consolidation": {"mode": "shadow", "poste": "general/L3"},
            "episodes": {"mode": "active", "every_s": 600, "plans_every_s": 1800, "plans_per_run": 20, "attest": True},
            "periods": {"tz": "Asia/Bangkok"}, "kardex": {"mode": "daily", "per_run": 5, "days": 60, "max_messages": 160},
            "privacy": {"cloud_context": "cloud_allowed", "pseudonymise": True, "kardex_cloud": "policy"},
            "stages": {},
            "rules": {"always": "all", "relevance_only_channels": ["contact"], "relevance_only_subjects": ["project:"]},
            "reconcile": {"mode": "decision", "candidates": 5, "batch": 12, "min_confidence": 0.5,
                          "state_ttl_days": 7}}

# The model-driven stages of the organic chain, each with its own switch (A2, 2026-11-19). A stage absent from
# [stages] follows [extraction] mode (the single switch of 2026-11-14), so an older config keeps its meaning.
STAGES = ("extraction", "catchup", "reconcile_existing", "subjects", "reconsolidation", "episode_summaries")


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


def stage(name: str) -> dict:
    """{"mode": "active" | "paused", "from": "stages" | "extraction"}: [stages] <name>, else [extraction] mode
    (owner, 2026-11-14: one pause for L3 extraction, subjects, reconsolidation and run-episode summaries). Raw events
    keep being ingested and indexed under any pause; what a paused stage would have done is taken up on resume."""
    if name not in STAGES:
        raise KeyError(f"unknown stage {name!r} (one of {', '.join(STAGES)})")
    own = (settings().get("stages") or {}).get(name)
    mode = own if own is not None else settings().get("extraction", {}).get("mode", "active")
    return {"mode": "paused" if str(mode) == "paused" else "active", "from": "stages" if own is not None else "extraction"}


def paused(name: str) -> bool:
    return stage(name)["mode"] == "paused"


def stages() -> dict:
    return {n: stage(n) for n in STAGES}


def extraction_paused() -> bool:
    """The L3 extraction stage (kept name: callers and tests of the 2026-11-14 switch)."""
    return paused("extraction")


def enabled(section: str, key: str = "enforce") -> bool:
    return bool(settings().get(section, {}).get(key, False))
