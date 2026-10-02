"""walter-router CLI: migrate | refresh | pick | prefer | alerts | verdict | status."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import alerts, choose, collect, db, dossier, execution, knowledge
from . import select as sel


def refresh(notify: bool = True, dry_run: bool = False) -> dict:
    with db.connect() as conn:
        run_id = conn.execute("insert into models.runs default values returning run_id").fetchone()["run_id"]
        conn.commit()
        try:
            report = {"sources": collect.collect_all(conn)}
            with conn.transaction():
                report["knowledge"] = knowledge.declare(conn)  # config/knowledge.json is the source of truth
            with conn.transaction():
                report["providers"] = execution.probe(conn)
            with conn.transaction():
                rows = sel.compute(conn)
                sel.save(conn, run_id, rows)
                report["selection_rows"] = len(rows)
                report["dossiers"] = dossier.build_all(conn, run_id)
                first = conn.execute("select count(*) as n from models.runs where status = 'ok'").fetchone()["n"] == 0
                report["alerts"] = {"challengers": alerts.challengers(conn, "baseline" if first else "open"),
                                    "top3": alerts.top3(conn), "unranked": alerts.unranked(conn),
                                    "stale": alerts.stale_sources(conn)}
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
        prefs = list(conn.execute("""select task, role, objective, pinned_model_id, pinned_variant, pinned_provider, watch
                                     from models.preferences order by task, role"""))
    return {"last_run": run, "sources": snaps, "alerts": open_alerts, "preferences": prefs}


RUN_MAX_AGE_H = 30  # the timer runs daily at 03:30 UTC


def health() -> dict:
    """Is the router fed and usable? ok=False lists what is wrong (used by walter_health and the failure alert)."""
    issues: list[str] = []
    with db.connect() as conn:
        last = conn.execute("""select run_id, status, finished_at, now() - coalesce(finished_at, started_at) as age, summary
                               from models.runs order by run_id desc limit 1""").fetchone()
        ok_run = conn.execute("select run_id, finished_at from models.runs where status = 'ok' order by run_id desc limit 1"
                              ).fetchone()
        if not last:
            issues.append("aucun refresh")
        else:
            if last["status"] == "failed":
                issues.append(f'dernier refresh en échec : {(last["summary"] or {}).get("error", "?")[:160]}')
            elif last["status"] == "running" and last["age"].total_seconds() > 3600:
                issues.append("refresh bloqué depuis plus d'une heure")
            for kind, info in ((last["summary"] or {}).get("sources") or {}).items():
                if "error" in info:
                    issues.append(f'source {kind} en erreur au dernier refresh : {info["error"][:120]}')
        if ok_run and (conn.execute("select now() - %s::timestamptz as a", (ok_run["finished_at"],)).fetchone()["a"]
                       .total_seconds() > RUN_MAX_AGE_H * 3600):
            issues.append(f'pas de refresh réussi depuis {str(ok_run["finished_at"])[:16]} UTC')
        sources = {r["kind"]: round(float(r["age_h"]), 1) for r in conn.execute(
            "select kind, extract(epoch from now() - fetched_at) / 3600 as age_h from models.latest_snapshots")}
        for kind, age in sources.items():
            if age > alerts.STALE_HOURS.get(kind, 48):
                issues.append(f"source {kind} vieille de {age:.0f} h")
        dossiers = conn.execute("select count(*) as n from models.latest_dossiers").fetchone()["n"]
        if not dossiers:
            issues.append("aucun dossier de tâche pour le dernier refresh réussi")
        providers = {r["provider"]: {"ok": r["ok"], "checked_at": r["checked_at"], "detail": r["detail"]}
                     for r in conn.execute("select * from models.provider_status")}
    warnings = [f'provider {p} indisponible au dernier test : {v["detail"][:100]}' for p, v in providers.items()
                if not v["ok"]]
    return {"ok": not issues, "issues": issues, "warnings": warnings, "providers": providers, "last_run": ok_run and {"run_id": ok_run["run_id"],
            "finished_at": ok_run["finished_at"]}, "sources_age_h": sources, "dossiers": dossiers}


def notify_failure() -> dict:
    """Called by systemd OnFailure: tell Monsieur on Telegram that the nightly refresh failed (one short message)."""
    try:
        h = health()
        why = "; ".join(h["issues"][:3]) or "voir journalctl -u walter-router-refresh"
    except Exception as exc:  # noqa: BLE001 — the database itself may be the problem
        why = f"base injoignable ({type(exc).__name__})"
    text = f"⚠️ Walter Router : le refresh de cette nuit a échoué — {why}. Les derniers choix restent utilisés."
    out = subprocess.run([str(alerts.HERMES), "send", "-t", "telegram", text], capture_output=True, text=True,
                         timeout=120)
    return {"sent": out.returncode == 0, "text": text}


def with_execution(conn, out: dict) -> dict:
    """Add the ordered Hermes routes to a chat decision (what the Hermes plugin runs, with fallbacks)."""
    task = conn.execute("select interface from models.tasks where task = %s", (out.get("task"),)).fetchone()
    if out.get("model_id") and task and task["interface"] == "chat":
        out["execution"] = execution.routes(conn, out["model_id"], out.get("variant") or "",
                                            preferred=out.get("provider"))
    return out


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
    k.add_argument("--role", help="favourite role, e.g. action / value / budget")
    k.add_argument("--require", choices=sorted(choose.REQUIREMENTS), help="hard constraint (unrestricted, open_weights)")
    f = sub.add_parser("prefer", help="record Monsieur's preference for a task")
    f.add_argument("task")
    f.add_argument("--objective", choices=("value", "best_available"))
    f.add_argument("--pin", help="favourite model as model_id[/variant], e.g. gpt-image-2-5-sunburst/max")
    f.add_argument("--provider")
    f.add_argument("--note")
    f.add_argument("--role", default="default")
    f.add_argument("--watch", choices=("quality", "dominance", "none"))
    a = sub.add_parser("alerts")
    a.add_argument("--all", action="store_true")
    v = sub.add_parser("verdict")
    v.add_argument("alert_id", type=int)
    v.add_argument("decision", choices=("adopted", "dismissed"))
    v.add_argument("--note")
    sub.add_parser("status")
    sub.add_parser("health", help="exit 1 when the router is not fed or not usable")
    sub.add_parser("probe", help="tiny live call per provider (Kie, OpenRouter, Arnict)")
    sub.add_parser("tasks", help="task keys, labels and interfaces (for tool descriptions)")
    sub.add_parser("notify-failure", help="Telegram message after a failed refresh (systemd OnFailure)")
    d = sub.add_parser("decide", help="free-text request -> role, model, route, workflow, brief")
    d.add_argument("task")
    d.add_argument("intent")
    d.add_argument("--level", choices=choose.LEVELS)
    sub.add_parser("declare", help="apply config/knowledge.json (profiles, roles, affinities)")
    o = sub.add_parser("dossier", help="the task's pre-computed dossier (what the router reads)")
    o.add_argument("task")
    args = p.parse_args(argv)

    if args.cmd == "migrate":
        out = {"applied": db.migrate()}
    elif args.cmd == "refresh":
        out = refresh(notify=not args.no_notify, dry_run=args.dry_run)
    elif args.cmd == "status":
        out = status()
    elif args.cmd == "health":
        out = health()
        json.dump(out, sys.stdout, indent=1, ensure_ascii=False, default=str)
        print()
        return 0 if out["ok"] else 1
    elif args.cmd == "probe":
        with db.connect() as conn:
            out = execution.probe(conn)
            conn.commit()
    elif args.cmd == "notify-failure":
        out = notify_failure()
    else:
        with db.connect() as conn:
            if args.cmd == "pick":
                out = with_execution(conn, choose.pick(conn, args.task, args.level, args.role, args.require))
            elif args.cmd == "prefer":
                out = choose.set_preference(conn, args.task, args.objective, args.pin, args.provider, args.note,
                                            args.role, args.watch)
            elif args.cmd == "decide":
                out = with_execution(conn, knowledge.decide(conn, args.task, args.intent, args.level))
            elif args.cmd == "tasks":
                out = list(conn.execute("select task, label, interface from models.tasks order by interface, task"))
            elif args.cmd == "dossier":
                out = dossier.latest(conn, args.task)
            elif args.cmd == "declare":
                out = knowledge.declare(conn)
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
