"""What the Router needs from the active Walter instance, asked through its public interface (`walter instance`).

The Router is software shared by every instance: whom it addresses, the instance's own declarations (knowledge,
subscriptions, declared offers, host bindings) and the agent runtime it configures belong to the instance.
Each value is read once per process.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
from pathlib import Path

SHIPPED = Path(__file__).resolve().parent / "config"
NEUTRAL_OWNER = "l'utilisateur"   # only when no instance answers


def _walter(*args: str) -> str | None:
    try:
        out = subprocess.run(["walter", "instance", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


@functools.lru_cache(maxsize=1)
def _show() -> dict:
    raw = _walter("show")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def owner() -> str:
    """How messages, notes and prompts name the person this instance serves (its declared address form)."""
    return _show().get("owner", {}).get("address") or NEUTRAL_OWNER


@functools.lru_cache(maxsize=None)
def config_path(name: str) -> Path:
    """An instance's own Router file (config/router/<name>) when it has one, else the shipped default."""
    found = _walter("config", "router", name)
    return Path(found) if found else SHIPPED / name


@functools.lru_cache(maxsize=1)
def host() -> dict:
    """Host bindings of the instance (config host.json): runtime profiles, cron jobs, publishing helpers."""
    return json.loads(config_path("host.json").read_text())


def hermes_active() -> bool:
    """Whether the instance still runs Hermes as a runtime the Router configures (host.json `hermes`; default active).
    Retired: nothing is applied to Hermes any more (sync-hermes, orchestrator) — walter-llm reads the Router itself."""
    return str(host().get("hermes", "active")) != "retired"


def _expand(value: str) -> Path:
    if value == "@instance" or value.startswith("@instance/"):
        root = _walter("path")
        if not root:
            raise RuntimeError("no active Walter instance for " + value)
        return Path(root) / value[len("@instance"):].lstrip("/")
    return Path(value).expanduser()


def host_path(key: str) -> Path | None:
    """A path binding of host.json (absolute, ~/ or @instance/); None when the instance has none."""
    value = host().get(key) or ""
    return _expand(value) if value else None


def own_file(name: str) -> Path:
    """Where the instance keeps its own copy of a Router file it writes (config/router/<name>)."""
    root = _walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return Path(root) / "config" / "router" / name


@functools.lru_cache(maxsize=1)
def hermes_home() -> Path:
    """The Hermes home this instance runs (HERMES_HOME, else the instance's declared harness home)."""
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"])
    found = _walter("harness", "hermes")
    return Path(found) if found else Path.home() / ".hermes"


def hermes_bin() -> Path:
    return hermes_home() / "hermes-agent" / "venv" / "bin" / "hermes"


def hermes_python() -> Path:
    return hermes_home() / "hermes-agent" / "venv" / "bin" / "python"


def child_env(**extra: str) -> dict:
    """Environment of a Hermes child process run on behalf of the Router."""
    return {**os.environ, "HOME": str(Path.home()), "HERMES_HOME": str(hermes_home()), **extra}




HERMES_ENV = hermes_home() / ".env"


def env_value(name: str) -> str | None:
    """A key from Hermes' 0600 .env (or the process environment), read at run time (never logged / put in a URL)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in HERMES_ENV.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        pass
    return os.environ.get(name)


def secret_value(name: str) -> str | None:
    """A key from the environment, else from the instance's vault (walter-secrets map or its declared keys). Keys
    that are not in Hermes' .env live only in Bitwarden (2026-10-30); the value is never logged or put in a URL."""
    value = env_value(name)
    if value:
        return value
    try:   # the walter-secrets module root (`walter path secrets`, not an instance path)
        secrets = subprocess.run(["walter", "path", "secrets"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not secrets:
        return None
    import sys
    if secrets not in sys.path:
        sys.path.insert(0, secrets)
    try:
        from walter_secrets.mapping import entry
        from walter_secrets.vault import VAULT
        e = entry(name)
        return VAULT.value(e["item_id"], e["field"])
    except Exception:  # noqa: BLE001 — unknown key or no vault session: the caller reports the key as missing
        return None


def state_file(name: str) -> Path:
    """A file the Router generates for the instance (state/router/<name>), e.g. the agents' brief."""
    root = _walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return Path(root) / "state" / "router" / name
