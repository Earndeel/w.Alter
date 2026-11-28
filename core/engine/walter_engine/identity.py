"""Who speaks through a door (Core identity, 2026-11-17).

The kind of a principal is resolved by the engine from the instance's account registry
(`@instance/config/core/principals.json`, defaults in `core/config/principals.json`), never taken from what a client
claims: a test account (`e2e`) is a `test` principal whatever its door says — its conversations are filed on the
`test` channel of the Run Plane, capped by walter-llm's test budget and never become objectives in the owner's list.
A client claiming `owner` for an account the instance does not list as the owner's is refused. Machine principals
(modules, other agents) stay machines. A test principal acts as the owner of its OWN test conversations only
(approvals, pinned tier) so the scenarios exercise the same paths, without ever touching the owner's.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import CORE_ROOT, _instance

KINDS = ("owner", "machine", "test")
_CACHE: dict = {"at": -1e9, "doc": None}


class IdentityError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def registry() -> dict:
    now = time.monotonic()
    if _CACHE["doc"] is not None and now - _CACHE["at"] < 30:
        return _CACHE["doc"]
    doc = {"owner": ["owner"], "test": ["e2e"]}
    try:
        path = Path(_instance().config("core", "principals.json"))
        doc = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — unreadable registry: the neutral defaults (fail towards test, never owner)
        try:
            doc = json.loads((CORE_ROOT / "config" / "principals.json").read_text())
        except Exception:  # noqa: BLE001
            pass
    doc = {"owner": [str(a) for a in doc.get("owner") or []], "test": [str(a) for a in doc.get("test") or []]}
    _CACHE.update(at=now, doc=doc)
    return doc


def resolve(principal: dict | None) -> dict:
    """{kind, id} as the instance knows it. Raises IdentityError(invalid_principal | unknown_owner_account)."""
    if not isinstance(principal, dict) or principal.get("kind") not in KINDS or not principal.get("id"):
        raise IdentityError("invalid_principal")
    pid, kind = str(principal["id"]), principal["kind"]
    reg = registry()
    if pid in reg["test"]:
        return {"kind": "test", "id": pid, **({"claimed": kind} if kind != "test" else {})}
    if kind == "owner" and pid not in reg["owner"]:
        raise IdentityError("unknown_owner_account", f"account {pid!r} is not one of the owner's accounts")
    return {"kind": kind, "id": pid}


def channel_of(principal: dict | None) -> str:
    return {"machine": "machine", "test": "test"}.get((principal or {}).get("kind"), "owner")


def acts_as_owner(principal: dict | None, session_principal: dict | None = None) -> bool:
    """Owner-only operations: the owner, or a test account on its own test conversation."""
    p = principal or {}
    if p.get("kind") == "owner":
        return True
    if p.get("kind") == "test" and session_principal is not None:
        return session_principal.get("kind") == "test" and session_principal.get("id") == p.get("id")
    return False
