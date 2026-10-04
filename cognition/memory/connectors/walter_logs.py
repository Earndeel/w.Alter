#!/usr/bin/env python3
"""walter-logs connector: every agent runtime's session log → walter_logs.* (see walter_memory/logs.py).

  sync   one incremental pass over every source (or --hermes/--claude/--codex/--dsh, or --file PATH)
  watch  daemon (walter-logs-watch.service): inotify on the sources, sync the changed one within ~2 s, and a full
         catch-up sweep every SWEEP_S (a missed notification is caught there; ids make re-reads free). No timer.
         Hermes changes also start walter-memory-hermes.service (core.events), at most every CORE_EVENTS_S.
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
PROFILE_CHECK_S = 600


def _locked():
    f = LOCK.open("a")
    fcntl.flock(f, fcntl.LOCK_EX)
    return f


def sync_hermes(profiles: list[str] | None = None) -> dict:
    out = {}
    for profile, path in logs.hermes_dbs().items():
        if profiles and profile not in profiles:
            continue
        total = {"rows": 0, "inserted": 0}
        while True:
            with connection() as conn:
                r = logs.sync_hermes(conn, profile, path)
            total["rows"] += r["rows"]; total["inserted"] += r["inserted"]
            if not r["more"]:
                break
        out[f"hermes:{profile}"] = total
    return out


def sync_files(paths: list[tuple[str, Path]]) -> dict:
    out = {"files": 0, "rows": 0, "inserted": 0}
    for runtime, p in paths:
        with connection() as conn:
            r = logs.sync_transcript(conn, runtime, p)
        out["files"] += 1; out["rows"] += r["rows"]; out["inserted"] += r["inserted"]
    return out


def sync_all(runtimes: list[str] | None = None) -> dict:
    runtimes = runtimes or ["hermes", "claude", "codex", "dsh"]
    out = {}
    if "hermes" in runtimes:
        out.update(sync_hermes())
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
    hermes_dirs = sorted({str(p.parent) for p in logs.hermes_dbs().values()})
    tree_dirs = [str(r) for r in logs.ROOTS.values() if r.exists()]
    threading.Thread(target=_watch, args=(hermes_dirs, False, q, stop), daemon=True).start()
    threading.Thread(target=_watch, args=(tree_dirs, True, q, stop), daemon=True).start()
    profiles_at_start = set(logs.hermes_dbs())
    last_sweep = last_core = last_profile_check = 0.0
    print(f"walter-logs watch: {len(hermes_dirs)} Hermes dirs, {tree_dirs}", flush=True)
    while True:
        changed: set[str] = set()
        try:
            changed.add(q.get(timeout=30))
            while True:
                changed.add(q.get_nowait())
        except Empty:
            pass
        now = time.time()
        hermes = sorted({p for p, path in logs.hermes_dbs().items()
                         for c in changed if c.startswith(str(path))})        # state.db, -wal, -shm
        files = sorted({(rt, Path(c)) for c in changed if c.endswith((".jsonl", ".jsonl.zstd"))
                        for rt in [logs.runtime_of(Path(c))] if rt and Path(c).exists()})
        try:
            with _locked():
                res = {}
                if now - last_sweep > SWEEP_S:
                    res = sync_all(); last_sweep = now
                else:
                    if hermes:
                        res.update(sync_hermes(hermes))
                    if files:
                        res["files"] = sync_files(files)
            if hermes and now - last_core > CORE_EVENTS_S:      # core.events (Monsieur's journal) follows
                subprocess.run(["systemctl", "start", "--no-block", "walter-memory-hermes.service"], check=False)
                last_core = now
            ins = sum(v.get("inserted", 0) for v in res.values() if isinstance(v, dict))
            if ins:
                print(f"{datetime.now(timezone.utc):%H:%M:%S}Z +{ins} {res}", flush=True)
            if res:
                ingestion.mark_success(logs.CONNECTOR)
        except Exception as e:  # noqa: BLE001 — the daemon survives; the sweep retries
            print(f"walter-logs: {type(e).__name__}: {e}", flush=True)
            ingestion.record_failure(logs.CONNECTOR, f"{type(e).__name__}: {e}"[:500])
            time.sleep(5)
        if now - last_profile_check > PROFILE_CHECK_S:
            last_profile_check = now
            if set(logs.hermes_dbs()) != profiles_at_start:    # a new Hermes profile: restart to watch it
                print("walter-logs: Hermes profiles changed, restarting", flush=True)
                stop.set()
                return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["sync", "watch"])
    for rt in ("hermes", "claude", "codex", "dsh"):
        ap.add_argument(f"--{rt}", action="store_true")
    ap.add_argument("--file")
    a = ap.parse_args()
    if a.action == "watch":
        return watch_main()
    with _locked():
        if a.file:
            p = Path(a.file).resolve()
            rt = logs.runtime_of(p)
            res = sync_files([(rt, p)]) if rt else {"error": "unknown runtime"}
        else:
            res = sync_all([rt for rt in ("hermes", "claude", "codex", "dsh") if getattr(a, rt)] or None)
    ingestion.mark_success(logs.CONNECTOR)
    print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
