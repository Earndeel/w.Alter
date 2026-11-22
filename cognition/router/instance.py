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


@functools.lru_cache(maxsize=1)
def gateway_journal() -> Path:
    """The walter-llm journal, resolved as the gateway does: the instance's config/llm/gateway.json first, the shipped
    default after (2026-11-22: reading the shipped default pointed at a file that does not exist)."""
    conf = _walter("config", "llm", "gateway.json")
    path = Path(conf) if conf else Path(__file__).resolve().parent / "llm" / "config" / "gateway.json"
    return _expand(json.loads(path.read_text())["log"])


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


def media_dir() -> Path:
    """Where the Router writes the media it generates (host.json `media_dir`, default
    @instance/workspace/generated/walter-router; was the Hermes home's generated/ until 2026-11-16)."""
    return host_path("media_dir") or _expand("@instance/workspace/generated/walter-router")


def secret_value(name: str) -> str | None:
    """A key the Router component is granted under NAME (Walter Secrets: instance accounts/<id>.toml, `allow` + [env],
    Bitwarden only), or the process environment when a caller injected it explicitly (tests, evaluation). None when
    no grant gives it: there is no fallback to a file (Hermes' .env was retired 2026-11-11). Never logged, never in a URL."""
    if os.environ.get(name):
        return os.environ[name]
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
        from walter_secrets import grants
        return grants.env_value(name, "router")
    except Exception:  # noqa: BLE001 — not granted or no vault session: the caller reports the key as missing
        return None


def state_file(name: str) -> Path:
    """A file the Router generates for the instance (state/router/<name>), e.g. the agents' brief."""
    root = _walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return Path(root) / "state" / "router" / name
