"""Settings: shipped defaults (/walter/ops/config/devboard.toml, neutral) overridden by the instance
(`walter instance config ops devboard.toml`). Paths come from the instance file or from `walter layout show`."""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DSN = "postgresql://hindsight@127.0.0.1:5433/hindsight"


@dataclass
class Config:
    docs_dir: Path = Path("docs")
    reports_dir: Path | None = None
    dsn: str = field(default_factory=lambda: os.environ.get("WALTER_DEVBOARD_DATABASE_URL", DEFAULT_DSN))
    required_provider: str = "claude-pro"
    subscription_prefix: str = "anthropic-pro"
    quota_pause_percent: float = 70.0
    idle_minutes: int = 30
    stale_days: int = 7
    since: str = "2026-10-01"
    listen_host: str = "127.0.0.1"
    port: int = 3093
    gateway_url: str = "http://127.0.0.1:8894"
    token_file: Path | None = None
    sessions_per_pass: int = 20


def _run_json(*cmd: str) -> dict:
    return json.loads(subprocess.run(list(cmd), capture_output=True, text=True, check=True, timeout=60).stdout)


def walter_root() -> Path:
    return Path(_run_json("walter", "layout", "show")["walter_root"])


def module_roots() -> list[Path]:
    """Every module root of the layout (their docs/ folders are read), each once."""
    seen, out = set(), []
    for m in _run_json("walter", "layout", "show")["modules"]:
        p = Path(m["root"]).resolve()
        if p not in seen and p.is_dir():
            seen.add(p)
            out.append(p)
    return out


def _config_file() -> Path | None:
    try:
        p = subprocess.run(["walter", "instance", "config", "ops", "devboard.toml"], capture_output=True, text=True,
                           check=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(p) if p and Path(p).is_file() else None


def load() -> Config:
    data: dict = {}
    f = _config_file()
    if f:
        data = tomllib.loads(f.read_text()).get("devboard", {})
    cfg = Config(docs_dir=Path(data.pop("docs_dir", "") or walter_root() / "docs"))
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, Path(value) if key in ("reports_dir", "token_file", "docs_dir") else value)
    if "WALTER_DEVBOARD_DATABASE_URL" in os.environ:
        cfg.dsn = os.environ["WALTER_DEVBOARD_DATABASE_URL"]
    return cfg
