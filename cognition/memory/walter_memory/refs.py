"""Typed references and opaque cursors of Walter Memory's reads (lot 3e, 2026-11-26).

A reference one read produces is directly usable by the read that knows its kind: `event:<id>` → memory_events,
`derived:<id>` → memory_view, `object:<id>` → vault_get, `log:<session>#<seq>` → logs_get / logs_timeline,
`entity:<uuid>` / `thread:<id>` → person_lookup, memory_events, vault_put links. Producers ADD a `typed_ref` field
beside their existing ones (an existing `ref` keeps its meaning); readers accept the typed form AND the legacy one.

A reference is an identifier, never an authorisation: decoding one only yields the arguments the caller could pass
anyway, and every read applies its own privacy check after decoding (same code path as the plain arguments).

A cursor is opaque to the caller and decoded only by the read that issued it: it carries the read's name and a
whitelisted set of its own arguments (a cursor of another read, or with any other key, is refused).
"""
from __future__ import annotations

import base64
import json
import re

KINDS = ("event", "derived", "object", "log", "entity", "thread", "task")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class RefError(ValueError):
    """invalid_request: the reference or cursor cannot be read by this tool (the message names the right reader)."""


READERS = {"event": "memory_events(event_id=…)", "derived": "memory_view(key=…)", "object": "vault_get(object_id=…)",
           "log": "logs_get(ref=…) / logs_timeline(ref=…)", "entity": "person_lookup / task_create(entity_id=…)",
           "thread": "memory_events(thread_id=…)", "task": "task_update(task_id=…)"}


def typed(kind: str, ident) -> str:
    if kind not in KINDS:
        raise RefError(f"unknown reference kind {kind!r}")
    return f"{kind}:{ident}"


def split(ref: str) -> tuple[str | None, str]:
    """`kind:id` → (kind, id); a value without a known kind prefix → (None, value) (legacy forms stay readable)."""
    ref = str(ref or "").strip()
    head, sep, rest = ref.partition(":")
    if sep and head in KINDS and rest:
        return head, rest
    return None, ref


def expect(ref: str, kind: str) -> str:
    """The id of a reference that must be of `kind` (a bare id is accepted as is). Another kind → RefError naming
    the tool that reads it."""
    k, ident = split(ref)
    if k not in (None, kind):
        raise RefError(f"a {k}: reference is read by {READERS.get(k, 'another tool')}, not here")
    return ident


def log_ref(ref: str) -> tuple[str, int | None]:
    """`log:<session>#<seq>`, the legacy `<session>#<seq>` of logs_search, or a bare session id."""
    ident = expect(ref, "log")
    session, sep, seq = ident.rpartition("#")
    if sep and seq.isdigit() and session:
        return session, int(seq)
    return ident, None


def encode_cursor(read: str, params: dict) -> str:
    raw = json.dumps({"r": read, "p": params}, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(read: str, token: str, allowed: set[str] | frozenset[str]) -> dict:
    try:
        pad = "=" * (-len(token) % 4)
        doc = json.loads(base64.urlsafe_b64decode(str(token).strip() + pad))
    except (ValueError, TypeError) as e:
        raise RefError("cursor is not one this read issued; pass the `cursor` value of its last answer as is") from e
    if not isinstance(doc, dict) or doc.get("r") != read or not isinstance(doc.get("p"), dict):
        raise RefError(f"cursor was issued by another read, not {read}")
    params = doc["p"]
    extra = set(params) - set(allowed)
    if extra:
        raise RefError(f"cursor carries arguments {sorted(extra)} that {read} does not page by")
    return {k: str(v) for k, v in params.items() if v not in (None, "")}
