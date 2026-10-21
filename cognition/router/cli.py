"""walter-router CLI: migrate | refresh | pick | prefer | alerts | verdict | status."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from walter_router import paths
from walter_router.analysis import aliases_admin
from walter_router.analysis import alerts
from walter_router.serve import media_exec
from walter_router.serve import choose
from walter_router.analysis.refresh import refresh
from walter_router.store import db
from walter_router.analysis import dossier
from walter_router.serve import execution
from walter_router.serve import intent
from walter_router.analysis import knowledge
from walter_router.research.agent import review
from walter_router.research.plans import subscriptions


def status() -> dict:
    with db.connect() as conn:
        snaps = list(conn.execute("""select distinct on (kind) kind, fetched_at, row_count from models.snapshots
                                     order by kind, fetched_at desc"""))
        run = conn.execute("select run_id, finished_at, status from models.runs order by run_id desc limit 1").fetchone()
        open_alerts = conn.execute("select kind, status, count(*) as n from models.alerts group by 1, 2 order by 1, 2").fetchall()
        prefs = list(conn.execute("""select task, role, objective, pinned_model_id, pinned_variant, pinned_provider, watch
                                     from models.preferences order by task, role"""))
    return {"last_run": run, "sources": snaps, "alerts": open_alerts, "preferences": prefs}


RUN_MAX_AGE_H = 54  # the cycle runs every 48 h


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
        ages = {r["kind"]: round(float(r["age_h"]), 1) for r in conn.execute(
            "select kind, extract(epoch from now() - fetched_at) / 3600 as age_h from models.latest_snapshots")}
        for kind, age in ages.items():
            if age > alerts.STALE_HOURS.get(kind, 48):
                issues.append(f"source {kind} vieille de {age:.0f} h")
        dossiers = conn.execute("select count(*) as n from models.latest_dossiers").fetchone()["n"]
        if not dossiers:
            issues.append("aucun dossier de tâche pour le dernier refresh réussi")
        providers = {r["provider"]: {"ok": r["ok"], "checked_at": r["checked_at"], "detail": r["detail"]}
                     for r in conn.execute("select * from models.provider_status")}
        subs = {r["sub_id"]: float(r["used_percent"]) for r in conn.execute(
            """select sub_id, used_percent from models.latest_subscription_usage
               where window_name = 'weekly' and source <> 'calibration'""")}
    warnings = [f'provider {p} indisponible au dernier test : {v["detail"][:100]}' for p, v in providers.items()
                if not v["ok"]]
    return {"ok": not issues, "issues": issues, "warnings": warnings, "providers": providers,
            "subscriptions": subs,  # weekly % per plan, information only (no routing effect)
            "last_run": ok_run and {"run_id": ok_run["run_id"],
            "finished_at": ok_run["finished_at"]}, "sources_age_h": ages, "dossiers": dossiers}


def notify_failure() -> dict:
    """Called by systemd OnFailure: tell the owner on Telegram that the nightly refresh failed (one short message)."""
    try:
        h = health()
        why = "; ".join(h["issues"][:3]) or "voir journalctl -u walter-router-refresh"
    except Exception as exc:  # noqa: BLE001 — the database itself may be the problem
        why = f"base injoignable ({type(exc).__name__})"
    with db.connect() as conn:  # The owner wants no noise: only when two cycles in a row failed (4 days blind)
        last = [r["status"] for r in conn.execute("select status from models.runs order by run_id desc limit 2")]
    if last != ["failed", "failed"]:
        return {"sent": False, "reason": "single failure: health only"}
    text = f"⚠️ Walter Router : deux cycles de suite ont échoué — {why}. Les derniers choix restent utilisés."
    out = subprocess.run([str(alerts.HERMES), "send", "-t", "telegram", text], capture_output=True, text=True,
                         timeout=120)
    return {"sent": out.returncode == 0, "text": text}


def feedback(conn, model: str, rating: int, task: str | None, note: str | None) -> dict:
    if model == "last":
        last = conn.execute("""select model_id, task from models.exec_log where ok and model_id is not null
                               order by at desc limit 1""").fetchone()
        if not last:
            raise KeyError("no routed run yet")
        model, task = last["model_id"], task or last["task"]
    conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (model,))
    fid = conn.execute("""insert into models.feedback (model_id, task, rating, note) values (%s, %s, %s, %s)
                          returning feedback_id""", (model, task, rating, note)).fetchone()["feedback_id"]
    return {"feedback_id": fid, "model_id": model, "task": task, "rating": rating}


def subscription_fallback(conn, task: str, exclude: str | None = None) -> dict | None:
    """Best model of the task (weighted composite) that the subscription (Codex) can run, with the reasoning level
    measured on the task's primary board."""
    from walter_router.analysis import scoring
    subs = {r["model_id"] for r in conn.execute("""select distinct o.model_id from models.offers o
                                                  join models.latest_snapshots s using (snapshot_id)
                                                  where o.access = 'subscription' and o.interface = 'chat'""")}
    for c in scoring.composite(conn, task):
        if c["model_id"] in subs and c["model_id"] != exclude:
            variants = [b["variant"] for b in c["boards"].values() if b.get("variant")]
            return {"model_id": c["model_id"], "variant": variants[0] if variants else "high",
                    "composite": c["composite"]}
    return None


def with_execution(conn, out: dict) -> dict:
    """Add the ordered Hermes routes to a chat decision (what the Hermes plugin runs, with fallbacks)."""
    task = conn.execute("select interface, requirements from models.tasks where task = %s", (out.get("task"),)).fetchone()
    if out.get("model_id") and task and task["interface"] == "chat":
        out["execution"] = execution.routes(conn, out["model_id"], out.get("variant") or "",
                                            preferred=out.get("provider"))
        basis = (out.get("follows") or {}).get("task") or out["task"]   # a 'level' poste falls back like its tier
        if basis != "general" and not any(r["access"] == "subscription" for r in out["execution"]):
            sub = subscription_fallback(conn, out["task"], exclude=out["model_id"])
            if sub:  # best model of this task reachable through the subscription, after the paid routes
                out["execution"] += [{**r, "fallback_for": out["model_id"]}
                                     for r in execution.routes(conn, sub["model_id"], sub["variant"])]
        fallback = knowledge.level_fallback(basis, out.get("level") or out.get("role"))
        if fallback:  # declared tier fallback, after every route of the pinned model
            fb_model, _, fb_variant = fallback.partition("/")
            out["execution"] += [{**r, "fallback_for": out["model_id"]}
                                 for r in execution.routes(conn, fb_model, fb_variant)]
        effort = (task["requirements"] or {}).get("reasoning")
        if effort:   # a poste's own reasoning level (voice_assist: minimal, the latency comes first)
            out["execution"] = [{**r, "reasoning": r.get("reasoning") or effort} for r in out["execution"]]
    elif out.get("model_id") and task and task["interface"] in ("rerank", "transcription", "embedding"):
        from walter_router.serve import media_exec  # service postes: modules call OpenRouter with this id (stt, rerank)
        out["openrouter_id"] = media_exec.openrouter_id(conn, out["model_id"])
    elif out.get("model_id") and task and task["interface"] in ("video", "image", "audio", "music"):
        from walter_router.serve import media_exec  # media: provider order of the model, then the category's fallback model
        cfg = media_exec._models().get(out["model_id"]) or {}
        mode = {"text_to_video": "t2v", "image_to_video": "i2v", "text_to_image": "t2i", "image_edit": "i2i"}.get(out["task"])
        out["providers"] = media_exec.choose_provider(conn, out["model_id"], task["interface"], None,
                                                      bool((cfg.get("kie") or {}).get(mode)),
                                                      media_exec.openrouter_id(conn, out["model_id"]))
        out["fallback_models"] = media_exec.fallback_models(conn, out["task"], out.get("role"), out["model_id"], mode)
        out["openrouter_id"] = media_exec.openrouter_id(conn, out["model_id"])   # modules calling OpenRouter (stt)
    return out


def route(conn, request: str, task: str | None = None, level: str | None = None) -> dict:
    """Free-text request -> Jev intent (task, video role, level, unrestricted) -> decision + execution routes.
    Without Jev (network/credits/contract error) the task must be given or defaults to 'general' + keywords."""
    try:
        jev = intent.classify(conn, request)
    except Exception as exc:  # noqa: BLE001 — keywords fallback
        jev = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    if not task:
        task = jev.get("task") if (jev.get("task_confidence") or 0) >= intent.MIN_CONFIDENCE else "general"
    if task == "general" and not level and jev.get("level"):
        level = jev["level"]
    out = with_execution(conn, knowledge.decide(conn, task, request, level, jev if "error" not in jev else None))
    return {**out, "intent": jev}


def _instance_env() -> int:
    """HERMES_HOME, LOG, CONTROL_ENV, LIBRARY_URL and ANALYSIS_PROMPT (the shipped analysis prompt
    rendered for the instance: its owner, its log folder), as shell assignments."""
    import shlex
    from walter_router import instance
    log = instance.host_path("log_dir")
    log.mkdir(parents=True, exist_ok=True)
    prompt = paths.AGENT_PROMPT.read_text()
    prompt = prompt.replace("{{log_dir}}", str(log))
    rendered = subprocess.run(["walter", "instance", "render"], input=prompt, capture_output=True, text=True,
                              timeout=30, check=True).stdout
    (log / "analysis-prompt.md").write_text(rendered)
    domain = instance.host().get("library_domain") or ""
    values = {"HERMES_HOME": instance.hermes_home(), "LOG": log,
              "CONTROL_ENV": instance.host_path("control_env") or "",
              "LIBRARY_URL": f"https://{domain}" if domain else "", "ANALYSIS_PROMPT": log / "analysis-prompt.md"}
    for k, v in values.items():
        print(f"{k}={shlex.quote(str(v))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="walter-router")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    r = sub.add_parser("refresh")
    r.add_argument("--no-notify", action="store_true")
    r.add_argument("--dry-run", action="store_true", help="compose the notification without sending it")
    r.add_argument("--skip-collect", action="store_true", help="re-derive the latest snapshots (no network)")
    k = sub.add_parser("pick")
    k.add_argument("task")
    k.add_argument("--level", choices=choose.LEVELS)
    k.add_argument("--role", help="favourite role, e.g. action / value / budget")
    k.add_argument("--require", choices=sorted(choose.REQUIREMENTS), help="hard constraint (unrestricted, open_weights)")
    f = sub.add_parser("prefer", help="record the owner's preference for a task")
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
    v.add_argument("--role", help="with a short number covering several roles: only this one")
    lb = sub.add_parser("library", help="the model library: per task/category model, chooser, providers, fallback")
    lb.add_argument("--json", action="store_true")
    hs = sub.add_parser("sync-hermes", help="write the router's postes into Hermes auxiliary jobs (compression…)")
    hs.add_argument("--apply", action="store_true", help="apply (config backup + graceful gateway restart)")
    hs.add_argument("--no-restart", action="store_true")
    pl = sub.add_parser("publish-library", help="rebuild and deploy the instance library page (host.json library_domain, Cloudflare Access)")
    pl.add_argument("--no-deploy", action="store_true")
    sb = sub.add_parser("subscriptions", help="the owner's subscriptions: quota meters, status, plan values")
    sb.add_argument("action", nargs="?", choices=["show", "refresh", "calibrate"], default="show")
    sb.add_argument("sub_id", nargs="?", help="calibrate: subscription id (anthropic-pro)")
    sb.add_argument("percent", nargs="?", type=float, help="calibrate: weekly %% shown by the vendor")
    sub.add_parser("status")
    sub.add_parser("health", help="exit 1 when the router is not fed or not usable")
    pr = sub.add_parser("probe", help="tiny live call per provider (Kie, OpenRouter, Arnict)")
    pr.add_argument("--provider", help="only this status key (kie, kie-codex, openrouter, arnict)")
    pr.add_argument("--timeout", type=int, default=90)
    sub.add_parser("tasks", help="task keys, labels and interfaces (for tool descriptions)")
    sub.add_parser("decision-chain", help="decision models to try, in order (consumed by walter-memory triage)")
    sub.add_parser("review", help="deterministic digest of the last cycle (input of the 48 h analysis agent)")
    aa = sub.add_parser("alias-add", help="link an unscored model id to the scored id it is (validated, with evidence)")
    aa.add_argument("key")
    aa.add_argument("model_id")
    aa.add_argument("--reason", required=True)
    aa.add_argument("--origin", default="agent")
    ar = sub.add_parser("alias-remove")
    ar.add_argument("key")
    sub.add_parser("alias-list")
    po = sub.add_parser("postes", help="fiche de poste ranking (orchestrator, agent_worker)")
    po.add_argument("poste", nargs="?", default="orchestrator")
    g = sub.add_parser("generate", help="generate an image / video / music / voice on the routed model")
    g.add_argument("request")
    g.add_argument("--task")
    g.add_argument("--role")
    g.add_argument("--image-url", action="append", dest="image_urls")
    g.add_argument("--voice", help="voice (tts), e.g. Algenib")
    g.add_argument("--style", help="delivery style (tts)")
    g.add_argument("--aspect-ratio")
    g.add_argument("--duration", type=int)
    g.add_argument("--resolution")
    g.add_argument("--paid-fallback", action="store_true", help="UI-only role (Flow): generate via Kie instead")
    g.add_argument("--no-craft", action="store_true", help="send the request as the prompt")
    lg = sub.add_parser("log-exec", help="record one routed execution attempt (JSON)")
    lg.add_argument("entry")
    fb = sub.add_parser("feedback", help="the owner's verdict on a model (rating -2..2)")
    fb.add_argument("model", help="model_id, or 'last' for the model of the last successful routed run")
    fb.add_argument("rating", type=int, choices=range(-2, 3))
    fb.add_argument("--task")
    fb.add_argument("--note")
    sub.add_parser("notify-failure", help="Telegram message after a failed refresh (systemd OnFailure)")
    d = sub.add_parser("decide", help="free-text request -> role, model, route, workflow, brief")
    d.add_argument("task")
    d.add_argument("intent")
    d.add_argument("--level", choices=choose.LEVELS)
    sub.add_parser("declare", help="apply config/knowledge.json (profiles, roles, affinities)")
    rt = sub.add_parser("route", help="free-text request -> Jev intent -> decision (task optional)")
    rt.add_argument("request")
    rt.add_argument("--task")
    rt.add_argument("--level", choices=choose.LEVELS)
    cl = sub.add_parser("classify", help="Jev intent only (task, video role, level, unrestricted)")
    cl.add_argument("request")
    o = sub.add_parser("dossier", help="the task's pre-computed dossier (what the router reads)")
    o.add_argument("task")
    sub.add_parser("instance-env", help="shell assignments of the instance bindings used by the cycle and the trigger")
    args = p.parse_args(argv)

    if args.cmd == "instance-env":
        return _instance_env()
    if args.cmd == "migrate":
        out = {"applied": db.migrate()}
    elif args.cmd == "decision-chain":
        with db.connect() as conn:
            out = {"chain": list(intent.chain(conn))}
    elif args.cmd == "refresh":
        out = refresh(notify=not args.no_notify, dry_run=args.dry_run, skip_collect=args.skip_collect)
    elif args.cmd == "status":
        out = status()
    elif args.cmd == "health":
        out = health()
        json.dump(out, sys.stdout, indent=1, ensure_ascii=False, default=str)
        print()
        return 0 if out["ok"] else 1
    elif args.cmd == "probe":
        with db.connect() as conn:
            out = execution.probe(conn, args.provider, args.timeout)
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
            elif args.cmd == "route":
                out = route(conn, args.request, args.task, args.level)
            elif args.cmd == "classify":
                out = intent.classify(conn, args.request)
            elif args.cmd == "log-exec":
                out = {"exec_id": execution.log(conn, json.loads(args.entry))}
            elif args.cmd == "feedback":
                out = feedback(conn, args.model, args.rating, args.task, args.note)
            elif args.cmd == "generate":
                out = media_exec.generate(conn, args.request, args.task, args.role, args.image_urls, args.aspect_ratio,
                                          args.duration, args.resolution, args.paid_fallback, not args.no_craft,
                                          voice=args.voice, style=args.style)
            elif args.cmd == "postes":
                from walter_router.analysis import postes as postes_mod
                out = {"current": postes_mod.current_orchestrator(), "ranking": postes_mod.rank(conn, args.poste)}
            elif args.cmd == "alias-add":
                out = aliases_admin.add(conn, args.key, args.model_id, args.reason, args.origin)
            elif args.cmd == "alias-remove":
                out = aliases_admin.remove(args.key)
            elif args.cmd == "alias-list":
                out = aliases_admin.listing()
            elif args.cmd == "review":
                out = review.digest(conn)
            elif args.cmd == "subscriptions":
                if args.action == "refresh":
                    subscriptions.refresh(conn, args.sub_id)
                elif args.action == "calibrate":
                    if not args.sub_id or args.percent is None:
                        p.error("calibrate needs <sub_id> <percent>")
                    subscriptions.calibrate(conn, args.sub_id, args.percent)
                out = subscriptions.state(conn)
            elif args.cmd == "sync-hermes":
                from walter_router.serve import hermes_sync
                out = hermes_sync.apply(conn, restart=not args.no_restart) if args.apply else hermes_sync.plan(conn)
            elif args.cmd == "publish-library":
                from walter_router.interface import library
                out = library.publish(conn, deploy=not args.no_deploy)
            elif args.cmd == "library":
                from walter_router.interface import library
                rs = library.rows(conn)
                if not args.json:
                    print(library.render(rs))
                    return 0
                out = rs
            elif args.cmd == "tasks":
                out = list(conn.execute("select task, label, interface from models.tasks where interface <> 'decisions' "
                                        "order by interface, task"))
            elif args.cmd == "dossier":
                out = dossier.latest(conn, args.task)
            elif args.cmd == "declare":
                out = knowledge.declare(conn)
            elif args.cmd == "alerts":
                rows = conn.execute("select * from models.alerts order by alert_id").fetchall() if args.all else alerts.pending(conn)
                out = rows
            else:
                out = alerts.verdict(conn, args.alert_id, args.decision, args.note, args.role)
                import subprocess   # the library page follows the owner's answer (background, non-blocking)
                wr = paths.ROOT / "bin" / "walter-router"   # after this command's commit
                subprocess.Popen(["sh", "-c", f'sleep 5; "{wr}" sync-hermes --apply; "{wr}" publish-library'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            conn.commit()
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
