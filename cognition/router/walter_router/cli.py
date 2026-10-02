"""walter-router CLI: migrate | refresh | pick | prefer | alerts | verdict | status."""
from __future__ import annotations

import argparse
import json
import sys

from . import alerts, choose, collect, db
from . import select as sel


def refresh(notify: bool = True, dry_run: bool = False) -> dict:
    with db.connect() as conn:
        run_id = conn.execute("insert into models.runs default values returning run_id").fetchone()["run_id"]
        conn.commit()
        try:
            report = {"sources": collect.collect_all(conn)}
            with conn.transaction():
                rows = sel.compute(conn)
                sel.save(conn, run_id, rows)
                report["selection_rows"] = len(rows)
                first = conn.execute("select count(*) as n from models.runs where status = 'ok'").fetchone()["n"] == 0
                report["alerts"] = {"challengers": alerts.challengers(conn, "baseline" if first else "open"),
                                    "unranked": alerts.unranked(conn), "stale": alerts.stale_sources(conn)}
                report["pruned_snapshots"] = collect.prune(conn)
                conn.execute("update models.runs set status = 'ok', finished_at = now(), summary = %s::jsonb where run_id = %s",
                             (json.dumps(report, default=str), run_id))
            if notify:
                with conn.transaction():
                    report["notify"] = alerts.notify(conn, dry_run=dry_run)
        except Exception as exc:
            conn.rollback()
            conn.execute("update models.runs set status = 'failed', finished_at = now(), summary = %s::jsonb where run_id = %s",
                         (json.dumps({"error": f"{type(exc).__name__}: {exc}"}), run_id))
            conn.commit()
            raise
        conn.commit()
    return {"run_id": run_id, **report}


def status() -> dict:
    with db.connect() as conn:
        snaps = list(conn.execute("""select distinct on (kind) kind, fetched_at, row_count from models.snapshots
                                     order by kind, fetched_at desc"""))
        run = conn.execute("select run_id, finished_at, status from models.runs order by run_id desc limit 1").fetchone()
        open_alerts = conn.execute("select kind, status, count(*) as n from models.alerts group by 1, 2 order by 1, 2").fetchall()
        prefs = list(conn.execute("select task, objective, pinned_model_id, pinned_variant from models.preferences"))
    return {"last_run": run, "sources": snaps, "alerts": open_alerts, "preferences": prefs}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-router")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    r = sub.add_parser("refresh")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--dry-run", action="store_true", help="compose the notification without sending it")
    k = sub.add_parser("pick")
    k.add_argument("task")
    k.add_argument("--level", choices=choose.LEVELS)
    f = sub.add_parser("prefer", help="record Monsieur's preference for a task")
    f.add_argument("task")
    f.add_argument("--objective", choices=("value", "best_available"))
    f.add_argument("--pin", help="favourite model as model_id[/variant], e.g. gpt-image-2-5-sunburst/max")
    f.add_argument("--provider")
    f.add_argument("--note")
    a = sub.add_parser("alerts")
    a.add_argument("--all", action="store_true")
    v = sub.add_parser("verdict")
    v.add_argument("alert_id", type=int)
    v.add_argument("decision", choices=("adopted", "dismissed"))
    v.add_argument("--note")
    sub.add_parser("status")
    args = p.parse_args(argv)

    if args.cmd == "migrate":
        out = {"applied": db.migrate()}
    elif args.cmd == "refresh":
        out = refresh(notify=not args.no_notify, dry_run=args.dry_run)
    elif args.cmd == "status":
        out = status()
    else:
        with db.connect() as conn:
            if args.cmd == "pick":
                out = choose.pick(conn, args.task, args.level)
            elif args.cmd == "prefer":
                out = choose.set_preference(conn, args.task, args.objective, args.pin, args.provider, args.note)
            elif args.cmd == "alerts":
                rows = conn.execute("select * from models.alerts order by alert_id").fetchall() if args.all else alerts.pending(conn)
                out = rows
            else:
                out = alerts.verdict(conn, args.alert_id, args.decision, args.note)
            conn.commit()
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
