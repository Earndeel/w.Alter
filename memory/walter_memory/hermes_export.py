"""Bounded, resumable raw Hermes archives. No harness or model dependency.

SQLite remains read-only. Each complete UTC day/profile is a deterministic
JSONL.zst archive, always local_only in the encrypted Raw Vault. Catalogue and
checkpoint commit together; a per-profile PostgreSQL lock serializes writers.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import zstandard


class ExportBusy(RuntimeError):
    pass


class ExportDeadline(RuntimeError):
    pass


def connector_name(profile: str, default_profile: bool = False) -> str:
    return "hermes" if default_profile else "hermes:" + profile


def pending_days(db, last_day: str | None, today: date) -> list[date]:
    """Skip empty dates, including empty profiles; never inspect row text."""
    for table, column in (("messages", "timestamp"), ("sessions", "started_at")):
        invalid = db.execute(f"select 1 from {table} where date({column}, 'unixepoch') is null "
                             f"or date({column}, 'unixepoch') < '0001-01-01' limit 1").fetchone()
        if invalid:
            raise ValueError("raw export source has invalid timestamps; watermark not advanced")
    lower = (date.fromisoformat(last_day) + timedelta(days=1)).isoformat() if last_day else "0001-01-01"
    rows = db.execute("""select day from (
        select distinct date(timestamp, 'unixepoch') as day from messages
        union select distinct date(started_at, 'unixepoch') as day from sessions
        ) where day >= ? and day < ? order by day""", (lower, today.isoformat()))
    return [date.fromisoformat(r[0]) for r in rows]


def write_day(db, path: Path, profile: str, day: date, deadline: float, default_profile: bool = False) -> dict:
    """One SQLite snapshot, one row at a time; private temporary output only."""
    start = datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()
    counts = {"messages": 0, "sessions": 0}
    db.execute("begin")
    try:
        with path.open("xb") as target:
            path.chmod(0o600)
            with zstandard.ZstdCompressor(level=12).stream_writer(target, closefd=False) as writer:
                def put(record):
                    if time.monotonic() >= deadline:
                        raise ExportDeadline("raw export time budget exhausted")
                    writer.write((json.dumps(record, ensure_ascii=False, default=str) + "\n").encode())
                put({"kind": "manifest", "version": 2, "profile": profile, "default_profile": default_profile, "day": day.isoformat()})
                # Include sessions referenced that day even if they began earlier.
                sessions = db.execute("""select * from sessions where
                    (started_at >= ? and started_at < ?) or id in
                    (select distinct session_id from messages where timestamp >= ? and timestamp < ?)
                    order by id""", (start, start + 86400, start, start + 86400))
                for row in sessions:
                    put({"kind": "session", **dict(row)}); counts["sessions"] += 1
                for row in db.execute("select * from messages where timestamp >= ? and timestamp < ? order by id",
                                      (start, start + 86400)):
                    put({"kind": "message", **dict(row)}); counts["messages"] += 1
    finally:
        db.rollback()
    return {**counts, "bytes": path.stat().st_size}


def export_profile(db, profile: str, store, *, max_days: int = 31, max_seconds: int = 900,
                   today: date | None = None, temp_root: str | None = None, default_profile: bool = False) -> dict:
    """The store commits save(path, profile, day, counts) before cursor advancement.

    A deadline interrupts a day without checkpoint advancement. A day limit
    returns remaining_days; the next call resumes. Completed days are immutable
    archives; late writes to old timestamps remain covered by logs/DB snapshots.
    """
    if not 1 <= max_days <= 366 or not 1 <= max_seconds <= 10800:
        raise ValueError("export bounds outside supported range")
    today = today or datetime.now(timezone.utc).date()
    deadline = time.monotonic() + max_seconds
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
    try:
        return _export_days(db, profile, store, max_days=max_days, today=today,
                            temp_root=temp_root, default_profile=default_profile, deadline=deadline)
    except sqlite3.OperationalError as exc:
        if time.monotonic() >= deadline:
            raise ExportDeadline("raw export SQLite time budget exhausted") from None
        raise
    finally:
        db.set_progress_handler(None, 0)


def _export_days(db, profile, store, *, max_days, today, temp_root, default_profile, deadline):
    days = pending_days(db, store.last_day(), today)
    report = {"profile": profile, "exported_days": 0, "reused_days": 0, "messages": 0, "bytes": 0,
              "remaining_days": len(days), "through": store.last_day()}
    for day in days[:max_days]:
        if time.monotonic() >= deadline:
            raise ExportDeadline("raw export time budget exhausted")
        if store.reuse(profile, day):
            report["reused_days"] += 1
        else:
            with tempfile.TemporaryDirectory(prefix="walter-hermes-export-", dir=temp_root) as temp:
                # Profile identity lives in archive/catalogue, not a filesystem path.
                path = Path(temp) / f"hermes-state-{day:%Y%m%d}.jsonl.zst"
                counts = write_day(db, path, profile, day, deadline, default_profile)
                store.save(path, profile, day, counts)
            report["exported_days"] += 1
            report["messages"] += counts["messages"]
            report["bytes"] += counts["bytes"]
        report["through"] = day.isoformat()
        report["remaining_days"] -= 1
    if not report["remaining_days"]:
        # Empty dates/profiles need no empty objects but have a checked watermark.
        report["through"] = max(store.last_day() or "0001-01-01", (today - timedelta(days=1)).isoformat())
        store.advance(report["through"])
    return report


class VaultExports:
    """Live storage adapter. Only technical identifiers may leave this class."""
    def __init__(self, profile: str, default_profile: bool = False):
        self.profile = profile
        self.default_profile = default_profile
        self.connector = connector_name(profile, default_profile)
        self.storage = None
        self.conn = None

    def __enter__(self):
        from .db import connect
        self.conn = connect(); self.conn.autocommit = True
        self.conn.execute("set statement_timeout = 30000")
        from .objects import s3
        from botocore.config import Config
        self.storage = s3(Config(connect_timeout=10, read_timeout=30,
            retries={"max_attempts": 2, "mode": "standard"},
            s3={"addressing_style": "path"}, signature_version="s3v4"))
        row = self.conn.execute("select pg_try_advisory_lock(184902, hashtext(%s)) as locked", (self.connector,)).fetchone()
        if not row["locked"]:
            self.conn.close(); self.conn = None
            raise ExportBusy("raw export already running for this profile")
        return self

    def __exit__(self, *exc):
        if self.conn is not None:
            self.conn.close()  # releases the session advisory lock even on failure

    def last_day(self):
        row = self.conn.execute("select cursor->>'last_day' as day from ingestion.checkpoints where connector=%s and stream='export'",
                                (self.connector,)).fetchone()
        return row["day"] if row else None

    def advance(self, day: str):
        from .ingestion import set_checkpoint
        set_checkpoint(self.connector, "export", {"last_day": day, "version": 2, "profile": self.profile, "default_profile": self.default_profile}, conn=self.conn)

    def _verify(self, row):
        from .objects import s3, BUCKETS
        if row["privacy_class"] != "local_only" or row["storage_zone"] != "secure" or row.get("purged_at"):
            raise RuntimeError("raw export object violates storage policy")
        head = self.storage.head_object(Bucket=BUCKETS["secure"], Key=row["storage_key"])
        if head["ContentLength"] != row["size_bytes"]:
            raise RuntimeError("raw export object size mismatch")

    def reuse(self, profile, day):
        # Legacy main exports predate the explicit profile field.
        with self.conn.transaction():
            row = self.conn.execute("""select privacy_class,storage_zone,storage_key,size_bytes,purged_at
                from core.objects where source='hermes_export'
                and source_ref->>'state_db_day'=%s
                and coalesce(source_ref->>'profile','main')=%s
                and coalesce((source_ref->>'default_profile')::boolean, not (source_ref ? 'profile'))=%s
                and purged_at is null limit 1""", (day.isoformat(), profile, self.default_profile)).fetchone()
            if row is None:
                return False
            self._verify(row)
            self.advance(day.isoformat())
            return True

    def save(self, path, profile, day, counts):
        from .objects import put_object
        with self.conn.transaction():
            row = put_object(path, "hermes_export", privacy_class="local_only", zone="secure",
                captured_at=datetime.combine(day, datetime.min.time(), timezone.utc),
                source_ref={"state_db_day": day.isoformat(), "profile": profile, "version": 2,
                            "messages": counts["messages"], "sessions": counts["sessions"],
                            "default_profile": self.default_profile}, conn=self.conn, storage_client=self.storage)
            self._verify(row)
            self.advance(day.isoformat())


def run(state_db: str, profile: str, *, default_profile: bool = False, **limits):
    from urllib.parse import urlsplit, unquote
    source = urlsplit(state_db) if state_db.startswith("file:") else None
    if source and source.netloc not in ("", "localhost"):
        raise ValueError("only local SQLite files are supported")
    path = Path(unquote(source.path) if source else state_db).resolve()
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        with VaultExports(profile, default_profile) as store:
            return export_profile(db, profile, store, temp_root="/var/tmp", default_profile=default_profile, **limits)
    finally:
        db.set_progress_handler(None, 0)
        db.close()
