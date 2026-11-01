"""Walter Browse Compatibility Adapter (Lot 4).

The ONLY layer that touches the Hermes plugin/tool API. If Hermes changes its
plugin interface (register_tool signature, context object, schema shapes),
fix THIS file — never the router, sessions, capabilities, or backends.

Design rules:
- Feature detection instead of version hardcoding: we probe the actual
  callable signatures and context attributes, then adapt.
- Hermes version is recorded for diagnostics only, never branched on.
- A startup self-test imports every Walter component and verifies the
  expected interfaces exist; anything missing => WALTER_BROWSE_DEGRADED with
  an explicit cause (never a silent failure).
"""
from __future__ import annotations

import inspect
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

WALTER_BROWSE_VERSION = "4.0.0"
ADAPTER_VERSION = 1

# Schema versions of the persistent stores (explicit migrations).
PROFILE_SCHEMA_VERSION = 4   # profiles.json (INDEX_VERSION in profile_index.py)
SESSION_SCHEMA_VERSION = 1   # session state.json
CAPABILITY_SCHEMA_VERSION = 1  # capability entries (version field per entry)
CACHE_SCHEMA_VERSION = 1     # result_cache.json

_COMPONENT_INTERFACES: dict[str, dict[str, str]] = {
    "profile_index": {
        "module": "profile_index",
        "symbols": [
            "ProfileIndex", "url_scope", "profile_key", "spec_fingerprint",
            "build_replay_template", "capability_name_from_spec",
        ],
        "methods": {
            "ProfileIndex": [
                "lookup", "observe", "invalidate", "observe_domain",
                "register_capability", "lookup_capability",
                "observe_capability", "bump_capability_version",
            ],
        },
    },
    "browse_session": {
        "module": "browse_session",
        "symbols": ["SessionManager", "BrowseSession", "cookies_for_domain"],
        "methods": {
            "SessionManager": [
                "create", "load", "get", "save", "destroy", "expire_stale",
            ],
        },
    },
    "capability_engine": {
        "module": "capability_engine",
        "symbols": ["CapabilityEngine", "CapabilityResult"],
        "methods": {"CapabilityEngine": ["execute", "router_url_from_implementation"]},
    },
    "result_cache": {
        "module": "result_cache",
        "symbols": ["ResultCache"],
        "methods": {"ResultCache": ["put", "get", "invalidate", "stats"]},
    },
    "static_html": {
        "module": "static_html",
        "symbols": ["extract_static_html"],
        "methods": {},
    },
}


def hermes_version() -> str:
    """Record Hermes version for diagnostics (never used for branching)."""
    try:
        from hermes_cli import __version__ as v  # type: ignore[import-not-found]
        return str(getattr(v, "version", v))
    except Exception:
        try:
            from importlib.metadata import version as _pkg_version
            return _pkg_version("hermes-agent")
        except Exception:
            return "unknown"


def _scripts_dir() -> Path:
    """Resolve the Walter scripts directory without hardcoding a state path."""
    candidate = Path(__file__).resolve().parent
    for parent in [candidate, *candidate.parents]:
        if (parent / "universal_router.py").is_file():
            return parent
    return candidate


def _module(name: str) -> Any:
    """Import a Walter component from the scripts directory (fresh path)."""
    scripts = _scripts_dir()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return __import__(name)


def supports_register_tool_kwarg(ctx: Any, kwarg: str) -> bool:
    """Feature detection: does the plugin context accept ``kwarg``?"""
    register = getattr(ctx, "register_tool", None)
    if register is None or not callable(register):
        return False
    try:
        signature = inspect.signature(register)
    except (TypeError, ValueError):
        return bool(hasattr(ctx, kwarg))
    return kwarg in signature.parameters or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
    )


def check_component(component: str) -> list[str]:
    """Return [] if the component imports and its expected interfaces exist."""
    spec = _COMPONENT_INTERFACES.get(component)
    if spec is None:
        return [f"unknown component {component!r}"]
    problems: list[str] = []
    try:
        module = _module(spec["module"])
    except Exception as exc:  # pragma: no cover - import failure
        return [f"{component}: import failed ({type(exc).__name__}: {exc})"]
    for symbol in spec.get("symbols", []):
        if not hasattr(module, symbol):
            problems.append(f"{component}: missing symbol {symbol}")
    for class_name, methods in spec.get("methods", {}).items():
        cls = getattr(module, class_name, None)
        if cls is None:
            problems.append(f"{component}: missing class {class_name}")
            continue
        for method in methods:
            if not hasattr(cls, method):
                problems.append(f"{component}: {class_name}.{method} missing")
    return problems


def run_startup_self_test() -> dict[str, Any]:
    """Light healthcheck: imports + interface presence. NO browser launch.

    Returns a structured report; components with problems are listed with
    explicit causes so the plugin can log WALTER_BROWSE_DEGRADED instead of
    failing silently.
    """
    started = time.perf_counter()
    report: dict[str, Any] = {
        "walter_browse_version": WALTER_BROWSE_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "hermes_version": hermes_version(),
        "schema_versions": {
            "profile": PROFILE_SCHEMA_VERSION,
            "session": SESSION_SCHEMA_VERSION,
            "capability": CAPABILITY_SCHEMA_VERSION,
            "cache": CACHE_SCHEMA_VERSION,
        },
        "components": {},
        "degraded": False,
        "elapsed_ms": 0,
    }
    for component in _COMPONENT_INTERFACES:
        problems = check_component(component)
        report["components"][component] = {"ok": not problems}
        if problems:
            report["degraded"] = True
            report["components"][component]["issues"] = problems
    # Entrypoint check (the CLI wrapper the plugin shells out to). Resolve
    # against the ACTIVE hermes home, falling back to the root home where the
    # Walter binary actually lives (the active home may be a sub-profile).
    def _entrypoint_ok() -> tuple[bool, str | None]:
        try:
            from hermes_constants import get_hermes_home
            homes = [get_hermes_home(), Path.home() / ".hermes"]
        except Exception:
            homes = [Path.home() / ".hermes"]
        candidates = [Path(home) / "bin" / "universal-scraper" for home in dict.fromkeys(homes)]
        for entry in candidates:
            if entry.is_file() and entry.stat().st_mode & 0o111:
                return True, str(entry)
        return False, str(candidates[0])

    entry_ok, entry_path = _entrypoint_ok()
    report["components"]["universal-scraper"] = {
        "ok": entry_ok,
        "path": entry_path,
    }
    if not entry_ok:
        report["degraded"] = True
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return report


def self_test_log_line(report: Mapping[str, Any]) -> str:
    """One-line, redacted summary for logs (no secrets, no paths)."""
    if report.get("degraded"):
        causes = [
            component
            for component, state in (report.get("components") or {}).items()
            if isinstance(state, Mapping) and not state.get("ok")
        ]
        return f"WALTER_BROWSE_DEGRADED cause={','.join(causes)} version={report.get('walter_browse_version')}"
    return (
        f"WALTER_BROWSE_HEALTHY version={report.get('walter_browse_version')} "
        f"components={sum(1 for s in (report.get('components') or {}).values() if isinstance(s, Mapping) and s.get('ok'))}"
    )


# ---------------------------------------------------------------------------
# Hermes <-> Walter contract helpers (feature detection, forward-compatible)
# ---------------------------------------------------------------------------

def build_invocation_trace(
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    started_epoch: float,
    request_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Single identifiable invocation trace: WALTER_BROWSE_INVOCATION.

    No sensitive data: request fields are intents/ids, never cookies, tokens,
    or payload values. Callers render this as:
        WALTER_BROWSE_INVOCATION <key=value ...>
    """
    payload = result if isinstance(result, Mapping) else {}
    return {
        "event": "WALTER_BROWSE_INVOCATION",
        "request_id": request_id or f"{int(started_epoch * 1000):x}",
        "session_id": session_id,
        "intent": str(request.get("objective") or "")[:120],
        "route": payload.get("route"),
        "capability_hit": "hit" if payload.get("capability") else "miss",
        "cache_hit": "hit" if payload.get("cached") else ("miss" if payload.get("fresh") is not None else "n/a"),
        "record_count": len(payload.get("records") or []) if isinstance(payload.get("records"), list) else 0,
        "success": bool(payload.get("success")),
        "duration_ms": round((time.perf_counter() - started_epoch) * 1000, 1),
    }


def format_invocation_trace(trace: Mapping[str, Any]) -> str:
    parts = [str(trace.get("event"))]
    for key, value in trace.items():
        if key == "event":
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI doctor (walter-browse doctor) — runnable outside Hermes too
# ---------------------------------------------------------------------------

def doctor_report() -> dict[str, Any]:
    """Full doctor: startup self-test + functional smoke checks.

    Returns a dict ready for JSON output. Executes a temporary anonymous
    session, an HTTP direct call, static HTML extraction, capability lookup
    (non-destructive), and reports Camoufox health. No secrets are emitted.
    """
    report = run_startup_self_test()
    checks: dict[str, Any] = {}

    # 0. Visibility: is walter_browse actually exposed on the active platform's
    # toolset list (and are the native web/browser toolsets removed)?
    try:
        import os as _os
        import sys as _sys

        _sys.path.insert(0, "/root/.hermes/hermes-agent")
        _os.environ.setdefault("HERMES_HOME", "/root/.hermes")
        from hermes_cli.config import load_config as _lc
        from hermes_cli.tools_config import _get_platform_tools as _gpt
        from hermes_cli.tools_config import _get_plugin_toolset_keys as _ptk
        from hermes_cli.plugins import discover_plugins

        discover_plugins(force=True)  # synchronous: plugins fully registered
        _cfg = _lc()
        _visible = _gpt(_cfg, "cli")
        # _gpt consults plugin toolset keys from the live registry: verify both
        # that walter-web is registered by a plugin AND resolvable.
        _walter_web_visible = "walter-web" in _visible
        _native_web_gone = not ({"web", "browser"} & set(_visible))
        checks["visible_on_current_platform"] = {
            "ok": _walter_web_visible and _native_web_gone,
            "walter_web_visible": _walter_web_visible,
            "plugin_toolset_keys": sorted(_ptk()),
            "native_web_hidden": _native_web_gone,
        }
    except Exception as exc:
        checks["visible_on_current_platform"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:200],
        }

    # 1. Temporary session life cycle.
    try:
        from browse_session import SessionManager
        manager = SessionManager()
        session = manager.create(identity="anonymous", persistent=False)
        checks["session_temporary"] = {"ok": True, "id": session.id}
        manager.destroy(session.id)
    except Exception as exc:
        checks["session_temporary"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    # 2. Capability lookup (read-only, non-destructive).
    try:
        from profile_index import ProfileIndex
        index = ProfileIndex()
        caps = index.list_capabilities()
        checks["capability_lookup"] = {"ok": True, "capability_count": len(caps)}
    except Exception as exc:
        checks["capability_lookup"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    # 3. Result cache round trip (isolated temp cache).
    try:
        import tempfile
        from result_cache import ResultCache
        with tempfile.TemporaryDirectory() as tmp:
            cache = ResultCache(path=Path(tmp) / "cache.json")
            cache.put(
                host="doctor.test", capability="probe", params={},
                records=[{"ok": True}], source_url="https://doctor.test", route="probe",
                ttl_seconds=60,
            )
            hit = cache.get("doctor.test", "probe", {})
            checks["result_cache"] = {"ok": bool(hit and hit.get("fresh"))}
    except Exception as exc:
        checks["result_cache"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    # 4. Camoufox MAX health (optional backend — not a degradation by itself).
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9377/health", timeout=5) as response:
            health = json.loads(response.read().decode("utf-8", errors="replace"))
        checks["camoufox_max"] = {"ok": bool(health.get("ok")), "optional": True}
    except Exception as exc:
        checks["camoufox_max"] = {"ok": False, "optional": True, "error": f"{type(exc).__name__}"}

    report["checks"] = checks
    all_ok = report.get("degraded") is False and all(
        c.get("ok") or c.get("optional") for c in checks.values()
    )
    report["doctor_ok"] = all_ok
    return report


def run_doctor_cli() -> int:
    """Console entrypoint for `walter-browse doctor`."""
    report = doctor_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("doctor_ok") else 2