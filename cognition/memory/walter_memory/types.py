"""Event taxonomy (A3): controlled, versioned, extensible — rows in core.event_types, validated here."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from .db import connection

SEED = Path(__file__).resolve().parent.parent / "event_types" / "v1.json"
_cache: dict[str, tuple[int, Draft202012Validator]] = {}
_loaded_at = 0.0
_lock = threading.Lock()


class UnknownEventType(ValueError):
    pass


class InvalidPayload(ValueError):
    pass


class RetiredEventType(UnknownEventType):
    """A type taken out of core.events on purpose (status 'retired'): writing it again is refused."""


_retired: set[str] = set()


def _load(force: bool = False) -> None:
    global _loaded_at
    with _lock:
        if not force and _cache and time.time() - _loaded_at < 60:
            return
        with connection() as conn:
            rows = conn.execute("""select distinct on (name) name, version, json_schema from core.event_types
                                   where status = 'active' order by name, version desc""").fetchall()
            retired = {r["name"] for r in conn.execute(
                "select name from core.event_types where status = 'retired'").fetchall()}
        _cache.clear()
        _retired.clear()
        _retired.update(retired - {r["name"] for r in rows})
        for r in rows:
            _cache[r["name"]] = (r["version"], Draft202012Validator(r["json_schema"]))
        _loaded_at = time.time()


def current_version(event_type: str) -> int:
    _load()
    if event_type not in _cache:
        _load(force=True)  # a type registered seconds ago by another process
    if event_type in _retired:
        raise RetiredEventType(f"event_type {event_type!r} is retired from core.events"
                               + (" (agent execution lives in walter_logs: see walter_memory/observability.py)"
                                  if event_type in ("tool.called", "skill.used") else ""))
    if event_type not in _cache:
        raise UnknownEventType(f"unknown event_type {event_type!r}: register it in core.event_types first")
    return _cache[event_type][0]


def validate(event_type: str, payload: dict) -> int:
    version = current_version(event_type)
    errors = sorted(_cache[event_type][1].iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise InvalidPayload(f"{event_type} v{version}: " + "; ".join(e.message for e in errors[:3]))
    return version


def register(name: str, description: str, json_schema: dict | None = None, version: int | None = None,
             status: str = "active") -> int:
    """Add a new type (or a new version of a type). Returns the version written. A retired type stays retired: only
    the seed file (status "retired") or a migration changes a status, never a plain re-registration."""
    with connection() as conn:
        if version is None:
            row = conn.execute("select coalesce(max(version), 0) + 1 as v from core.event_types where name = %s",
                               (name,)).fetchone()
            version = row["v"]
        conn.execute("""insert into core.event_types (name, version, description, json_schema, status)
                        values (%s,%s,%s,%s,%s)
                        on conflict (name, version) do update set description = excluded.description,
                                                                  json_schema = excluded.json_schema,
                            status = case when excluded.status = 'retired' then 'retired'
                                          else core.event_types.status end""",
                     (name, version, description, json.dumps(json_schema or {"type": "object"}), status))
    _load(force=True)
    return version


def sync_seed(path: Path = SEED) -> int:
    """Load the versioned seed file (v1 types). '$ref_same_as' copies another type's schema."""
    items = json.loads(path.read_text())
    by_name = {i["name"]: i for i in items}
    for item in items:
        schema = item.get("json_schema") or {"type": "object"}
        if "$ref_same_as" in schema:
            schema = by_name[schema["$ref_same_as"]]["json_schema"]
        register(item["name"], item["description"], schema, version=item.get("version", 1),
                 status=item.get("status", "active"))
    return len(items)


def list_types() -> list[dict]:
    with connection() as conn:
        return conn.execute("select name, version, status, description from core.event_types order by name, version").fetchall()
