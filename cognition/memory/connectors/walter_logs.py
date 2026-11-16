#!/usr/bin/env python3
"""walter-logs connector: every agent runtime's session log → walter_logs.* (see walter_memory/logs.py).

  sync   one incremental pass over every source (or --claude/--codex/--dsh, or --file PATH)
  keys   backfill walter_logs.events.event_key (migration 015) for rows that have none; reports later copies
  watch  daemon (walter-logs-watch.service): inotify on the sources, sync the changed one within ~2 s, and a full
         catch-up sweep every SWEEP_S (a missed notification is caught there; ids make re-reads free). No timer.
         DSH changes also start `walter-memory agent-sessions --dsh` (core.events), at most every CORE_EVENTS_S.
Hermes (state.db per profile) was a source until its removal on 2026-11-16; its sessions stay in walter_logs.
"""
from __future__ import annotations

import argparse
import fcntl
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walter_memory import ingestion, logs  # noqa: E402
from walter_memory.db import connection  # noqa: E402

LOCK = Path("/run/lock/walter-logs.lock")
SWEEP_S = 3600
CORE_EVENTS_S = 20


def _locked():
    f = LOCK.open("a")
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def sync_files(paths: list[tuple[str, Path]]) -> dict:
    out = {"files": 0, "rows": 0, "inserted": 0}
    for runtime, p in paths:
        with connection() as conn:
            r = logs.sync_transcript(conn, runtime, p)
        out["files"] += 1; out["rows"] += r["rows"]; out["inserted"] += r["inserted"]
    return out


def sync_all(runtimes: list[str] | None = None) -> dict:
    runtimes = runtimes or ["claude", "codex", "dsh"]
    out = {}
    for rt in ("claude", "codex", "dsh"):
        if rt in runtimes:
            out[rt] = sync_files([(rt, p) for p in logs.transcript_files(rt)])
    return out


# ───────────────────────── watch daemon ─────────────────────────
def _watch(paths: list[str], recursive: bool, q: Queue, stop: threading.Event) -> None:
    from watchfiles import watch
    for changes in watch(*paths, recursive=recursive, debounce=1500, step=200, stop_event=stop,
                         raise_interrupt=False, ignore_permission_denied=True):
        for _change, path in changes:
            q.put(path)


def watch_main() -> int:
    q: Queue = Queue()
    stop = threading.Event()
    tree_dirs = [str(r) for r in logs.ROOTS.values() if r.exists()]
    threading.Thread(target=_watch, args=(tree_dirs, True, q, stop), daemon=True).start()
    last_sweep = last_dsh = 0.0
    dsh_pending = False
    print(f"walter-logs watch: {tree_dirs}", flush=True)
    while True:
        changed: set[str] = set()
        try:
            changed.add(q.get(timeout=30))
            while True:
                changed.add(q.get_nowait())
        except Empty:
            pass
        now = time.time()
        files = sorted({(rt, Path(c)) for c in changed if c.endswith((".jsonl", ".jsonl.zstd"))
                        for rt in [logs.runtime_of(Path(c))] if rt and Path(c).exists()})
        try:
            with _locked():
                res = {}
                if now - last_sweep > SWEEP_S:
                    res = sync_all(); last_sweep = now
                elif files:
                    res["files"] = sync_files(files)
            # A change inside the 20 s window stays pending (the loop wakes at least every 30 s) instead of waiting for
            # the next write.
            dsh_pending = dsh_pending or any(rt == "dsh" for rt, _ in files)
            # Engine lot E2 (2026-11-10): the engine's sessions reach core.events because their files changed, not
            # because a hook ran at the end of a turn (the engine's native events no longer call walter_hook.py).
            # agent-sessions is incremental and locked: a run that overlaps the hook's own journal steps aside.
            if dsh_pending and now - last_dsh > CORE_EVENTS_S:
                subprocess.Popen(["walter-memory", "agent-sessions", "--dsh"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                last_dsh, dsh_pending = now, False
            ins = sum(v.get("inserted", 0) for v in res.values() if isinstance(v, dict))
            if ins and (len(res) > 2 or ins >= 200):     # sweeps and big catch-ups only (journal stays quiet)
                print(f"{datetime.now(timezone.utc):%H:%M:%S}Z +{ins} {res}", flush=True)
            if res:
                ingestion.mark_success(logs.CONNECTOR)
        except Exception as e:  # noqa: BLE001 — the daemon survives; the sweep retries
            print(f"walter-logs: {type(e).__name__}: {e}", flush=True)
            ingestion.record_failure(logs.CONNECTOR, f"{type(e).__name__}: {e}"[:500])
            time.sleep(5)


def backfill_keys(only: str | None = None) -> dict:
    """event_key on every stored row that has none (the first copy of each event); later copies stay NULL."""
    from walter_memory.db import connect
    out = {"sessions": 0, "keyed": 0, "duplicates": 0}
    with connect() as conn:
        sids = [r["session_id"] for r in conn.execute(
            """select distinct session_id from walter_logs.events where event_key is null
               and (%s::text is null or session_id = %s) order by 1""", (only, only)).fetchall()]
    for sid in sids:
        with connection() as conn:
            todo, dups = logs.session_keys(conn, sid)
            with conn.cursor() as cur:
                cur.executemany("""update walter_logs.events e set event_key = %s where session_id = %s and seq = %s
                                   and not exists (select 1 from walter_logs.events k
                                                   where k.session_id = e.session_id and k.event_key = %s)""",
                                [(k, sid, seq, k) for k, seq in todo])
        out["sessions"] += 1; out["keyed"] += len(todo); out["duplicates"] += len(dups)
        if len(dups) >= 100:
            print(f"  {sid}: {len(todo)} keyed, {len(dups)} later copies", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["sync", "watch", "keys"])
    for rt in ("claude", "codex", "dsh"):
        ap.add_argument(f"--{rt}", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--session", help="keys: only this session")
    a = ap.parse_args()
    if a.action == "watch":
        return watch_main()
    if a.action == "keys":
        with _locked():
            print(backfill_keys(a.session))
        return 0
    with _locked():
        if a.file:
            p = Path(a.file).resolve()
            rt = logs.runtime_of(p)
            res = sync_files([(rt, p)]) if rt else {"error": "unknown runtime"}
        else:
            res = sync_all([rt for rt in ("claude", "codex", "dsh") if getattr(a, rt)] or None)
    ingestion.mark_success(logs.CONNECTOR)
    print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
