"""Settings: shipped defaults (/walter/ops/config/devboard.toml, neutral) overridden by the instance
(`walter instance config ops devboard.toml`). Paths come from the instance file or from `walter layout show`."""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Walter's PostgreSQL address: the variable above, else the host's one declaration (/etc/walter/database.url, no
# password: credentials come from ~/.pgpass), else the default. Renamed hindsight → walter on 2026-11-21.
def _host_dsn() -> str | None:
    try:
        return open(os.environ.get("WALTER_DATABASE_URL_FILE", "/etc/walter/database.url")).read().strip() or None
    except OSError:
        return None


DEFAULT_DSN = _host_dsn() or "postgresql://walter@127.0.0.1:5433/walter"


@dataclass
class Config:
    docs_dir: Path = Path("docs")
    reports_dir: Path | None = None
    dsn: str = field(default_factory=lambda: os.environ.get("WALTER_DEVBOARD_DATABASE_URL", DEFAULT_DSN))
    required_provider: str = "claude-pro"
    subscription_prefix: str = "anthropic-pro"
    idle_minutes: int = 30
    stale_days: int = 7
    since: str = "2026-10-01"
    listen_host: str = "127.0.0.1"
    port: int = 3093
    gateway_url: str = "http://127.0.0.1:8894"
    token_file: Path | None = None
    sessions_per_pass: int = 20
    dev_cwds: list = field(default_factory=list)      # Claude Code sessions opened there are development sessions
    excluded_cwds: list = field(default_factory=list)   # never read, whatever the runtime (W.Alter mode profiles)
    owner_name: str = "le propriétaire"              # how the page names the owner (« corrigé par … »)
    # The owner's buttons (2026-11-15): served only on the loopback listener (behind Walter Web's sign-in panel).
    actions_host: str = "127.0.0.1"
    actions_port: int = 0                             # 0 = no buttons
    engine_url: str = "http://127.0.0.1:8895"
    engine_token_file: Path | None = None             # @instance/bootstrap/engine/api.token
    engine_interface: str = "web"                     # door of the resumes: the owner's own (full access)
    engine_account: str = "owner"
    resume_level: str = ""                            # Router text tier pinned on the resumes (L1–L3), "" = the plan's
    notify_command: list = field(default_factory=list)   # end of a resume told to the owner (text appended)
    follow_seconds: int = 20
    resume_lost_hours: float = 8.0


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


def _instance_path(value: str) -> str:
    """`@instance/…` (contract notation) → the instance's folder."""
    value = str(value)
    if not value.startswith("@instance/"):
        return value
    root = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, check=True,
                          timeout=30).stdout.strip()
    return root.rstrip("/") + "/" + value.removeprefix("@instance/")


def load() -> Config:
    data: dict = {}
    f = _config_file()
    if f:
        data = tomllib.loads(f.read_text()).get("devboard", {})
    cfg = Config(docs_dir=Path(data.pop("docs_dir", "") or walter_root() / "docs"))
    for key, value in data.items():
        if hasattr(cfg, key):
            if key in ("reports_dir", "token_file", "docs_dir", "engine_token_file"):
                value = Path(_instance_path(value))
            setattr(cfg, key, value)
    if "WALTER_DEVBOARD_DATABASE_URL" in os.environ:
        cfg.dsn = os.environ["WALTER_DEVBOARD_DATABASE_URL"]
    return cfg


def eligible(cfg: "Config", runtime: str, cwd: str | None) -> bool:
    """A development session: never in an excluded folder; Claude Code only in dev_cwds; Codex anywhere else."""
    c = (cwd or "").rstrip("/")
    if any(c == p.rstrip("/") or c.startswith(p.rstrip("/") + "/") for p in cfg.excluded_cwds):
        return False
    return runtime == "codex" or cwd in cfg.dev_cwds
