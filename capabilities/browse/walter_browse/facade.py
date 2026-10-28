"""First-class Hermes tool for the Walter Browsing Stack.

The model submits a URL and a semantic extraction contract.  The Walter
router, not the model, chooses between learned replay, Scrapling, Camoufox
Max, and Webtop CDP.  The plugin invokes the stable wrapper rather than
importing the optional Scrapling runtime into the Hermes interpreter.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_MAX_URL_LENGTH = 8192
_MAX_OBJECTIVE_LENGTH = 2000
_MAX_FIELDS = 40
_MAX_ALIASES_PER_FIELD = 16
_MAX_RECORDS = 100
_ROUTER_TIMEOUT_SECONDS = 240

WALTER_BROWSE_SCHEMA: dict[str, Any] = {
    "name": "walter_browse",
    "description": (
        "THE default web tool. Use it for ANY web need — from a quick search "
        "to complex browsing: current information, web search, reading a page, "
        "collecting structured data (prices, listings, offers), exploring a "
        "site, using a session/capability, comparing pages. It automatically "
        "picks the lightest enough path (search-lite, HTTP, static HTML, "
        "learned API replay/capability, stealth browser) — never a heavy "
        "browser when something lighter works. It also learns: repeated site "
        "journeys become reusable capabilities. For a simple question, just "
        "pass query=... and you get compact results in ~1s. For a page, pass "
        "url=... (+ objective). For structured data add expected_fields. "
        "Internal engines (search backends, Scrapling, Camoufox, replay, "
        "profiles) are chosen by the router — do not try to force them. "
        "mode=auto is always right except when diagnosing a backend."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Web search query (search-lite: fast, no browser). Mutually exclusive with url. E.g. 'who won the F1 GP yesterday', 'Tokyo weather now'.",
            },
            "url": {
                "type": "string",
                "description": "Public http(s) URL to read/extract/search on; no localhost or private network targets. Mutually exclusive with query.",
            },
            "objective": {
                "type": "string",
                "description": "Plain-language goal: 'read this page', 'find prices', 'compare offers', 'check my account with my session'. Used for intent and traces.",
            },
            "profile": {
                "type": "string",
                "description": "Known Walter site profile, when one exists; mutually exclusive with expected_fields.",
            },
            "capability": {
                "type": "string",
                "description": "Learned site capability, e.g. 'site.tld/market_search'; executes the virtual API directly (fast path). Optional.",
            },
            "session_id": {
                "type": "string",
                "description": "Walter session id to use (persistent cookies/identity); optional, never pasted secrets.",
            },
            "expected_fields": {
                "type": "object",
                "description": (
                    "Mapping of canonical field names to one or more aliases found in the site's payload, "
                    "for example {\"price\":[\"price\",\"totalPrice\"]}. Optional when content_only=true or "
                    "objective only asks to read/summarize a page; required for structured extraction."
                ),
                "additionalProperties": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
            },
            "content_only": {
                "type": "boolean",
                "description": "True = return a clean readable text/HTML content of the page instead of structured records (reading mode). Default false.",
            },
            "required_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Canonical fields that must be present for a usable result.",
            },
            "min_records": {
                "type": "integer",
                "minimum": 1,
                "maximum": _MAX_RECORDS,
                "description": "Minimum number of normalized records required for success.",
            },
            "score_threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 1000,
                "description": "Optional semantic candidate score threshold used by the router.",
            },
            "mode": {
                "type": "string",
                "enum": ["auto", "scrapling", "camoufox", "webtop"],
                "description": "Use auto for normal operation; explicit modes are for diagnostics only.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


def _error(message: str, *, url: str | None = None) -> str:
    payload: dict[str, Any] = {"success": False, "error": message}
    if url:
        payload["url"] = url
    return json.dumps(payload, ensure_ascii=False)


def _validate_url(raw_url: Any) -> str:
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("url must be a non-empty http(s) URL")
    url = raw_url.strip()
    if len(url) > _MAX_URL_LENGTH:
        raise ValueError(f"url exceeds the {_MAX_URL_LENGTH}-character limit")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must use http(s) and include a hostname")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise ValueError("url must target a public host; local hosts are blocked")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("url must target a public host; private or reserved IPs are blocked")
    return url


def _normalize_expected_fields(raw_fields: Any) -> dict[str, list[str]]:
    if not isinstance(raw_fields, Mapping) or not raw_fields:
        raise ValueError("expected_fields must be a non-empty object when profile is absent")
    if len(raw_fields) > _MAX_FIELDS:
        raise ValueError(f"expected_fields supports at most {_MAX_FIELDS} fields")
    normalized: dict[str, list[str]] = {}
    for raw_name, raw_aliases in raw_fields.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("expected_fields contains an empty canonical field name")
        aliases = [raw_aliases] if isinstance(raw_aliases, str) else raw_aliases
        if not isinstance(aliases, (list, tuple)) or not aliases:
            raise ValueError(f"expected_fields[{name!r}] must be a non-empty string list")
        if len(aliases) > _MAX_ALIASES_PER_FIELD:
            raise ValueError(f"expected_fields[{name!r}] has too many aliases")
        cleaned = [str(alias).strip() for alias in aliases if str(alias).strip()]
        if not cleaned:
            raise ValueError(f"expected_fields[{name!r}] has no usable aliases")
        normalized[name] = cleaned
    return normalized


def _validate_request(args: Any) -> dict[str, Any]:
    if not isinstance(args, Mapping):
        raise ValueError("walter_browse arguments must be an object")

    query_raw = args.get("query")
    query = str(query_raw).strip() if query_raw is not None else ""
    if len(query) > 512:
        raise ValueError("query is too long")
    url = _validate_url(args.get("url")) if args.get("url") is not None else ""
    if query and url:
        raise ValueError("query and url are mutually exclusive")
    if not query and not url:
        raise ValueError("provide query (web search) or url (page)")

    profile_raw = args.get("profile")
    profile = str(profile_raw).strip() if profile_raw is not None else ""
    if profile and len(profile) > 128:
        raise ValueError("profile name is too long")
    if query and profile:
        raise ValueError("query is incompatible with profile")

    capability_raw = args.get("capability")
    capability = str(capability_raw).strip() if capability_raw is not None else ""
    if capability and len(capability) > 128:
        raise ValueError("capability name is too long")
    if profile and capability:
        raise ValueError("profile and capability are mutually exclusive")
    if query and capability:
        raise ValueError("query is incompatible with capability")

    has_fields = args.get("expected_fields") is not None
    content_only = bool(args.get("content_only"))
    if profile and has_fields:
        raise ValueError("profile and expected_fields are mutually exclusive")
    if not profile and not capability and not has_fields and not content_only and not query:
        raise ValueError(
            "provide expected_fields (structured extraction), content_only=true "
            "(page reading), profile, capability, or query (search)"
        )

    expected_fields = None
    if has_fields:
        expected_fields = _normalize_expected_fields(args.get("expected_fields"))
    required_raw = args.get("required_fields", [])
    if not isinstance(required_raw, (list, tuple)):
        raise ValueError("required_fields must be a string list")
    required_fields = [str(field).strip() for field in required_raw if str(field).strip()]
    if expected_fields is not None:
        unknown = sorted(set(required_fields) - set(expected_fields))
        if unknown:
            raise ValueError(f"required_fields not present in expected_fields: {', '.join(unknown)}")

    session_id_raw = args.get("session_id")
    session_id = str(session_id_raw).strip() if session_id_raw is not None else ""
    if session_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("session_id must contain only letters, digits, underscores or hyphens")

    min_records = args.get("min_records", 1)
    if isinstance(min_records, bool) or not isinstance(min_records, int) or not 1 <= min_records <= _MAX_RECORDS:
        raise ValueError(f"min_records must be an integer between 1 and {_MAX_RECORDS}")

    score_threshold = args.get("score_threshold", 25.0)
    if isinstance(score_threshold, bool) or not isinstance(score_threshold, (int, float)):
        raise ValueError("score_threshold must be a number")
    if not 0 <= float(score_threshold) <= 1000:
        raise ValueError("score_threshold must be between 0 and 1000")

    mode = str(args.get("mode", "auto")).strip().lower()
    if mode not in {"auto", "scrapling", "camoufox", "webtop"}:
        raise ValueError("mode must be auto, scrapling, camoufox, or webtop")

    objective_raw = args.get("objective", "")
    objective = str(objective_raw).strip()
    if len(objective) > _MAX_OBJECTIVE_LENGTH:
        raise ValueError(f"objective exceeds the {_MAX_OBJECTIVE_LENGTH}-character limit")

    return {
        "query": query or None,
        "url": url or None,
        "objective": objective,
        "profile": profile or None,
        "capability": capability or None,
        "session_id": session_id or None,
        "content_only": content_only,
        "expected_fields": expected_fields,
        "required_fields": required_fields,
        "min_records": min_records,
        "score_threshold": float(score_threshold),
        "mode": mode,
    }


def _resolve_router_command() -> list[str]:
    """Walter-owned entrypoint, independent of the calling harness and PATH."""
    import os
    executable = Path(os.environ.get("WALTER_BROWSE_COMMAND", "/opt/walter-browse/bin/universal-scraper"))
    if not executable.is_file():
        raise FileNotFoundError("Walter Browse executable is unavailable")
    return [str(executable)]


def _build_router_command(request: Mapping[str, Any]) -> list[str]:
    if request.get("query"):
        # search-lite: the lightest route of the universal web entry point.
        return [
            *_resolve_router_command(),
            "--search", str(request["query"]),
            "--search-count", str(max(1, min(int(request.get("min_records", 5) or 5), 8))),
        ]
    command = [*_resolve_router_command(), "--url", str(request["url"])]
    if request.get("capability"):
        command.extend(["--capability", str(request["capability"])])
        if request.get("session_id"):
            command.extend(["--session-id", str(request["session_id"])])
        return command
    if request.get("profile"):
        command.extend(["--profile", str(request["profile"])])
    elif request.get("content_only"):
        # Reading mode: ask the router for the page's textual content.
        command.extend(
            [
                "--expected-fields",
                json.dumps(
                    {"content": ["content", "text", "description", "body"]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "--required-field", "content",
            ]
        )
    else:
        command.extend(
            [
                "--expected-fields",
                json.dumps(request["expected_fields"], ensure_ascii=False, separators=(",", ":")),
            ]
        )
    for field in request["required_fields"]:
        command.extend(["--required-field", field])
    if request.get("session_id"):
        command.extend(["--session-id", str(request["session_id"])])
    command.extend(
        [
            "--min-records",
            str(request["min_records"]),
            "--score-threshold",
            str(request["score_threshold"]),
            "--mode",
            str(request["mode"]),
        ]
    )
    return command


# Network exits (Monsieur, 2026-10-28): page reads (HTTP probes, static HTML, Scrapling) leave through the owner's
# real local IP (walter-exit-local, fail closed, per-host budget), never the server's bare IP; search APIs
# authenticated by a key (Brave) leave from the server, which keeps the owner's IP out of search-engine volume.
# Browser engines use their own exits (Camoufox: walter-exit-local; Chromium: the parents' Freebox).
_LOCAL_EXIT = "http://127.0.0.1:1084"


def _router_env(request: Mapping[str, Any]) -> dict[str, str]:
    import os
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(k, None)
    if request.get("query"):
        return env
    proxy = os.environ.get("WALTER_BROWSE_EXIT_LOCAL", _LOCAL_EXIT)
    env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, http_proxy=proxy, https_proxy=proxy, WALTER_BROWSE_PROXY=proxy,
               NO_PROXY="127.0.0.1,localhost,::1", no_proxy="127.0.0.1,localhost,::1")
    return env


def _run_router(request: Mapping[str, Any]) -> dict[str, Any]:
    command = _build_router_command(request)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_ROUTER_TIMEOUT_SECONDS,
            check=False,
            env=_router_env(request),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "url": request["url"],
            "objective": request["objective"],
            "error": f"Walter Browsing Stack timed out after {_ROUTER_TIMEOUT_SECONDS} seconds",
        }
    except OSError as exc:
        return {
            "success": False,
            "url": request["url"],
            "objective": request["objective"],
            "error": f"Could not start Walter Browsing Stack: {exc}",
        }

    stdout = (completed.stdout or "").strip()
    if not stdout:
        detail = ""
        return {
            "success": False,
            "url": request["url"],
            "objective": request["objective"],
            "error": detail or "Walter Browsing Stack returned no JSON result",
            "router_exit_code": completed.returncode,
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {
            "success": False,
            "url": request["url"],
            "objective": request["objective"],
            "error": f"Walter Browsing Stack returned invalid JSON: {exc}",
            "router_exit_code": completed.returncode,
        }
    if not isinstance(payload, dict):
        return {
            "success": False,
            "url": request["url"],
            "objective": request["objective"],
            "error": "Walter Browsing Stack returned a non-object JSON result",
            "router_exit_code": completed.returncode,
        }

    records = payload.get("records")
    usable = isinstance(records, list) and len(records) >= request["min_records"]
    # search-lite route: the payload carries `results`, not `records`.
    if not usable and request.get("query"):
        results = payload.get("results")
        usable = bool(payload.get("success")) and isinstance(results, list) and len(results) > 0
    payload["success"] = bool(completed.returncode == 0 and usable)
    payload["objective"] = request["objective"]
    payload["router_exit_code"] = completed.returncode
    if not payload["success"] and not payload.get("error"):
        payload["error"] = "The extraction contract was not satisfied"
    return payload


async def _handle_walter_browse(args: Mapping[str, Any], **_: Any) -> str:
    import time as _time

    started = _time.perf_counter()
    try:
        request = _validate_request(args)
    except ValueError as exc:
        return _error(str(exc), url=args.get("url") if isinstance(args, Mapping) else None)

    try:
        result = await asyncio.to_thread(_run_router, request)
    except Exception as exc:  # pragma: no cover - final plugin boundary
        logger.error("walter_browse failed: %s", type(exc).__name__)
        return _error(f"Walter Browsing Stack failed: {type(exc).__name__}", url=request["url"])

    return json.dumps(result, ensure_ascii=False, default=str)



browse = _handle_walter_browse
