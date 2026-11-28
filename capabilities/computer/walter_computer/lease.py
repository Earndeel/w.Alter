"""Explicit task reservation. Every operation must run under DeviceCallLock.

This coordinates cooperating Walter clients, not humans or programs outside Walter.
Reservations expire after a bounded TTL even if their process crashes.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
import uuid

LEASE_ACTIONS = frozenset({"lease_acquire", "lease_renew", "lease_release", "lease_status"})


class WorkflowLease:
    def __init__(self, lock_path, *, now=time.monotonic):
        self.path = Path(str(lock_path) + ".lease.json")
        self.now = now
        self.principal = uuid.uuid4().hex

    def _owner(self, session):
        return hashlib.sha256((self.principal + ":" + session).encode()).hexdigest()

    def _read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError("untrusted device reservation")
            row = json.loads(stream.read(4097))
        if not isinstance(row, dict) or not isinstance(row.get("owner"), str) or not isinstance(row.get("lease_id"), str) or not math.isfinite(float(row.get("expires", float("nan")))):
            raise PermissionError("invalid device reservation")
        return row if row["expires"] > self.now() else None

    def _write(self, row):
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(row, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def allowed(self, session):
        row = self._read()
        return row is None or row["owner"] == self._owner(session)

    def handle(self, session, action, args):
        row = self._read()
        owned = row is not None and row["owner"] == self._owner(session)
        if action == "lease_status":
            return {"ok": True, "reserved": row is not None, "owned": owned,
                    "expires_in_seconds": max(0, round(row["expires"] - self.now(), 2)) if row else 0}
        if action == "lease_release":
            if row and not owned:
                return {"ok": False, "code": "device_reserved"}
            if owned:
                self.path.unlink()
            return {"ok": True, "released": owned}
        if action not in {"lease_acquire", "lease_renew"}:
            raise ValueError("unknown reservation operation")
        if row and not owned:
            return {"ok": False, "code": "device_reserved"}
        if action == "lease_renew" and not owned:
            return {"ok": False, "code": "lease_expired"}
        ttl = float(args.get("ttl_seconds", 120))
        if not math.isfinite(ttl) or not 1 <= ttl <= 300:
            raise ValueError("lease TTL must be between 1 and 300 seconds")
        row = {"owner": self._owner(session), "lease_id": row["lease_id"] if owned else uuid.uuid4().hex,
               "expires": self.now() + ttl}
        self._write(row)
        return {"ok": True, "reserved": True, "lease_id": row["lease_id"], "expires_in_seconds": ttl}
