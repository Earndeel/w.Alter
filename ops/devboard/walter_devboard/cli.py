"""walter-devboard — the development board (README.md)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="walter-devboard", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply the schema migrations")
    sub.add_parser("sync-docs", help="read documents and decisions (no model)")
    sub.add_parser("bus", help="bus consumer: agent turns mark sessions to read (service)")
    sub.add_parser("due", help="read what is due: idle sessions, decisions, tasks; record commits (timer)")
    b = sub.add_parser("backfill", help="register and read past development sessions and tasks")
    b.add_argument("--since")
    b.add_argument("--limit", type=int, default=20)
    sub.add_parser("correct", help='owner correction, JSON on stdin: {"ref","field","value","reason"}')
    sub.add_parser("serve", help="the web page and read API (listen_host:port of the instance settings)")
    sub.add_parser("status", help="what the board waits on: pause, failed reads, sessions to read")
    sub.add_parser("path-unit", help="print walter-devboard-docs.path for this instance's watched folders")
    r = sub.add_parser("read-session", help="read one session now (guards apply)")
    r.add_argument("session_id")
    a = ap.parse_args(argv)
    from . import config, db
    if a.cmd == "bus":
        from . import consumer
        consumer.main()
        return 0
    if a.cmd == "serve":
        import uvicorn
        cfg = config.load()
        uvicorn.run("walter_devboard.server:app", host=cfg.listen_host, port=cfg.port, log_level="warning",
                    proxy_headers=False)
        return 0
    if a.cmd == "correct":
        from . import correct
        try:
            with db.connection() as c:
                out = correct.correct(c, json.loads(sys.stdin.read() or "{}"))
        except (ValueError, TypeError) as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 2
    elif a.cmd in ("due", "backfill", "read-session"):
        from . import backfill, docs, due, reading
        cfg = config.load()
        with db.autocommit() as c:
            if not db.try_lock(c):
                print(json.dumps({"busy": True}))
                return 0
            if a.cmd == "due":
                out = {"docs": docs.sync(c, cfg), **due.run(cfg, c)}
            elif a.cmd == "backfill":
                out = {"docs": docs.sync(c, cfg), **backfill.run(cfg, c, since=a.since, limit=a.limit)}
            else:
                out = {"state": reading.read_session(cfg, c, a.session_id)}
    elif a.cmd == "path-unit":
        from . import docs
        print(docs.path_unit(config.load()), end="")
        return 0
    elif a.cmd == "status":
        from . import status
        with db.autocommit() as c:
            out = status.report(c)
    elif a.cmd == "migrate":
        out = {"applied": db.migrate()}
    elif a.cmd == "sync-docs":
        from . import docs
        cfg = config.load()
        with db.connection() as c:
            out = docs.sync(c, cfg)
    print(json.dumps(out, ensure_ascii=False, default=str, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
