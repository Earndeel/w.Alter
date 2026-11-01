"""The reserve: archived skills stay findable, and come back by themselves when an agent needs one.

Nobody has to guess in advance which skills will be used again (Monsieur, 2026-11-01). A skill the curator (or a
reorganisation) put in archive/ is still searched; the moment an agent reads it, it is restored to
skills/<domain>/<name> with a commit and a ledger entry. A skill that was *merged* is not restored: its text lives,
unchanged, inside the skill that absorbed it, and reads point there.
"""
from __future__ import annotations

import shutil
import threading
from datetime import datetime, timezone

from . import registry, store

_ARCHIVE_KEYS = ("archived_at", "archived_by", "archived_reason", "reserve", "domain")


def merged_into(s: store.Skill) -> str | None:
    """The active skill that holds this archived skill's text, if it was merged."""
    hub = s.meta.get("absorbed_into")
    return hub if hub and store.find(hub, include_archived=False) else None


def restorable(s: store.Skill) -> bool:
    return s.state == "archived" and not s.meta.get("absorbed_into")


def restore(name: str, reason: str, runtime: str | None = None) -> store.Skill | None:
    """archive/<name> → skills/<domain>/<name>. Idempotent; never overwrites an active skill."""
    with store.write_lock():
        s = store.find(name, include_archived=True)
        if s is None or not restorable(s):
            return s
        domain = s.meta.get("domain") or "misc"
        dst = store.ROOT / "skills" / domain / s.name
        if dst.exists():
            return store.find(name, include_archived=False)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s.path), str(dst))
        meta = {k: v for k, v in store.read_sidecar(dst).items() if k not in _ARCHIVE_KEYS}
        meta |= {"restored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "restore_reason": reason}
        store.write_sidecar(dst, meta)
        commit = store._commit(f"reserve: restore {name} to {domain}/ ({reason})", ["skills", "archive"],
                               "walter-skills", store.ROOT)
    try:
        registry.ledger("reserve", "restore", name, commit, {"domain": domain, "reason": reason, "runtime": runtime})
    except Exception:
        pass  # the move is done and committed; the ledger is evidence, not a gate
    _refresh_async()
    return store.find(name, include_archived=False)


def _refresh_async() -> None:
    """New engine (search sees the restored skill) and a republished index, without blocking the read."""
    def run():
        try:
            from . import domains
            from .retrieval import engine
            engine(reload=True)
            domains.build()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()
