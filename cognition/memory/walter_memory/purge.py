"""Break-glass purge (A9): really delete a secret or wrongly ingested data — everywhere, backups included.

Normal history is append-only; this is the explicit exception. Dry-run by default. On --execute it:
  1. deletes matching core.events (+ idempotence keys), derived items citing them, objects (bytes + registry row
     marked purged), privacy detections refs (the Hindsight tables were dropped on 2026-11-09);
  2. takes a fresh PG dump and offsite backup, then deletes every OLDER PG dump (local + Drive), since those
     still contain the purged data; state.db backups too when --statedb is given (the matching messages are
     redacted in state.db first, with the gateway stopped by the operator);
  3. writes system.purges with fingerprints only (sha256 of ids), never the content.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess

from .db import connection
from .objects import BUCKETS, s3

OFFSITE = "gdrive:W.Alter Backups"


def _fp(values) -> list[str]:
    return [hashlib.sha256(str(v).encode()).hexdigest() for v in values]


def select_targets(conn, *, event_ids=None, object_refs=None, pattern=None) -> dict:
    t = {"events": [], "objects": [], "derived": []}
    if event_ids:
        t["events"] += [r["event_id"] for r in conn.execute(
            "select event_id from core.events where event_id = any(%s::uuid[])", (event_ids,)).fetchall()]
    if pattern:
        t["events"] += [r["event_id"] for r in conn.execute(
            "select event_id from core.events where content ~* %s or payload::text ~* %s", (pattern, pattern)).fetchall()]
        t["objects"] += [r["id"] for r in conn.execute(
            "select id from core.objects where purged_at is null and (derived_text ~* %s or original_name ~* %s)",
            (pattern, pattern)).fetchall()]
        t["derived"] += [r["item_id"] for r in conn.execute(
            "select item_id from core.derived_items where content ~* %s", (pattern,)).fetchall()]
    if object_refs:
        t["objects"] += [r["id"] for r in conn.execute(
            "select id from core.objects where id::text = any(%s) or sha256 = any(%s)", (object_refs, object_refs)).fetchall()]
    if t["events"]:
        t["derived"] += [r["item_id"] for r in conn.execute(
            "select item_id from core.derived_items where source_event_ids && %s::uuid[]", (t["events"],)).fetchall()]
    return {k: sorted(set(v), key=str) for k, v in t.items()}


def purge(*, reason: str, requested_by: str, event_ids=None, object_refs=None, pattern=None,
          execute=False, rewrite_backups=True) -> dict:
    with connection() as conn:
        targets = select_targets(conn, event_ids=event_ids, object_refs=object_refs, pattern=pattern)
        counts = {k: len(v) for k, v in targets.items()}
        selector = {"event_ids": len(event_ids or []), "object_refs": len(object_refs or []),
                    "pattern_sha256": hashlib.sha256(pattern.encode()).hexdigest() if pattern else None}
        fps = _fp([*targets["events"], *targets["objects"], *targets["derived"]])
        if not execute:
            conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status)
                            values (%s,%s,%s,%s,%s,'dry_run')""",
                         (requested_by, reason, json.dumps(selector), fps, json.dumps(counts)))
            return {"status": "dry_run", "counts": counts}
        conn.execute("set local walter.purge = 'on'")
        src_refs = [r["ref"] for r in conn.execute(
            "select source || ':' || source_id ref from core.events where event_id = any(%s::uuid[])",
            (targets["events"],)).fetchall()] if targets["events"] else []
        if targets["events"]:
            conn.execute("delete from core.event_keys where event_id = any(%s::uuid[])", (targets["events"],))
            conn.execute("delete from core.events where event_id = any(%s::uuid[])", (targets["events"],))
        if targets["derived"]:
            conn.execute("delete from core.derived_items where item_id = any(%s::uuid[])", (targets["derived"],))
        # derived copies of the text: search index and privacy detection refs
        refs = [*targets["events"], *targets["derived"], *targets["objects"]]
        if refs:
            conn.execute("delete from search.chunks where ref_id = any(%s::uuid[])", (refs,))
            # model decisions recorded from them (their outcome may quote the purged text)
            conn.execute("delete from processing.decisions where refs && %s::uuid[]", (refs,))
            conn.execute("delete from privacy.detections where target_ref = any(%s)", ([str(r) for r in refs] + src_refs,))
        for oid in targets["objects"]:
            row = conn.execute("select storage_key, storage_zone from core.objects where id = %s", (oid,)).fetchone()
            s3().delete_object(Bucket=BUCKETS[row["storage_zone"]], Key=row["storage_key"])
            conn.execute("""update core.objects set purged_at = now(), derived_text = null, original_name = null,
                                meta = '{}', source_ref = '{}' where id = %s""", (oid,))
        conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status,
                            backups_rewritten) values (%s,%s,%s,%s,%s,'executed',%s)""",
                     (requested_by, reason, json.dumps(selector), fps, json.dumps(counts), rewrite_backups))
    if targets["objects"]:
        # S3 deletes through rclone land in Drive's trash: empty it (drive.file scope = only W.Alter's own files)
        subprocess.run(["rclone", "cleanup", "gdrive:"], check=False)
    if rewrite_backups:
        _rewrite_backups()
    return {"status": "executed", "counts": counts, "backups_rewritten": rewrite_backups}


def _rewrite_backups() -> None:
    """Fresh dump + offsite copy, then remove every older PG backup (local + Drive) that still holds the data."""
    subprocess.run(["systemctl", "start", "walter-pg-backup"], check=True)
    subprocess.run(["systemctl", "start", "walter-offsite-backup"], check=True)
    local = sorted(subprocess.run("ls -1t /root/.hermes/backups/pg/*.dump", shell=True, capture_output=True,
                                  text=True).stdout.split())
    newest = max(local, key=lambda p: re.search(r"(\d{8}T\d{6}Z)", p).group(1)) if local else None
    for p in local:
        if p != newest:
            subprocess.run(["shred", "-u", p], check=False)
    remote = subprocess.run(["rclone", "lsf", f"{OFFSITE}/pg/"], capture_output=True, text=True).stdout.split()
    if remote:
        keep = max(remote)
        for f in remote:
            if f != keep:
                subprocess.run(["rclone", "deletefile", "--drive-use-trash=false", f"{OFFSITE}/pg/{f}"], check=True)
