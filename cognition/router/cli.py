"""walter-router CLI: migrate | refresh | pick | prefer | alerts | verdict | status | route | run | web …"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from walter_router import instance, paths
from walter_router.analysis import aliases_admin
from walter_router.analysis import alerts
from walter_router.serve import media_exec
from walter_router.serve import agent_view, choose, named
from walter_router.serve import run as run_job
from walter_router.analysis.refresh import refresh
from walter_router.store import db
from walter_router.health import health, notify_failure, status
from walter_router.serve.routes import route, with_execution
from walter_router.analysis import dossier
from walter_router.serve import execution
from walter_router.serve import intent
from walter_router.analysis import knowledge
from walter_router.research.agent import review
from walter_router.plan import subscriptions




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


def _instance_env() -> int:
    """HERMES_HOME, LOG, CONTROL_ENV, LIBRARY_URL and ANALYSIS_PROMPT (the shipped analysis prompt
    rendered for the instance: its owner, its log folder), as shell assignments."""
    import shlex
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


def build_parser() -> argparse.ArgumentParser:
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
    k.add_argument("--require", choices=sorted(choose.REQUIREMENTS), help="hard constraint (unrestricted, open_weights, video_input)")
    k.add_argument("--agent", action="store_true", help="the view an agent gets (choice, why, routes with prices)")
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
    bt = sub.add_parser("button", help="a pressed Telegram button of a Router alert (data wr:<a|d>:<ref>[:<role>]), "
                                       "for the Telegram door: records the verdict, prints {ok, toast, drop}")
    bt.add_argument("data")
    dbn = sub.add_parser("decision-bench", help="decision models judged against the owner's blind answers, use by use "
                         "(build cases | run models | label on Telegram | status | report)")
    dbn.add_argument("action", choices=("build", "run", "label", "status", "report"))
    dbn.add_argument("--models", help="run: comma-separated decision offers (default: the bench's list)")
    dbn.add_argument("--samples", type=int, default=3)
    lb = sub.add_parser("library", help="the model library: per task/category model, chooser, providers, fallback")
    lb.add_argument("--json", action="store_true")
    hs = sub.add_parser("sync-hermes", help="Hermes follows the router: auxiliary jobs, OpenRouter host order per model, cron postes")
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
    sub.add_parser("analyze", help="48 h cycle step 2: the research agent, delegated to Walter Engine; the Router "
                                   "applies its name links (validated) and writes the report")
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
    rt = sub.add_parser("route", help="free-text request -> intent (decision model) -> decision + execution routes")
    rt.add_argument("request")
    rt.add_argument("--task")
    rt.add_argument("--level", choices=choose.LEVELS)
    rt.add_argument("--context", help="one line on what the conversation was about before this request")
    rt.add_argument("--agent", action="store_true", help="the view an agent gets (choice, why, routes with prices)")
    rt.add_argument("--model", help="a model named by the owner: exactly that one (or why it cannot run)")
    rt.add_argument("--provider", help="with --model: that provider only (openrouter, kie, codex, arnict)")
    rn = sub.add_parser("run", help="do the job on the chosen model: JSON spec on stdin (goal, request, task, level, "
                                    "model, provider, context, toolsets…; media: role, image_urls…) -> JSON result")
    rn.add_argument("--dry-run", action="store_true", help="the decision only")
    tr = sub.add_parser("transcribe", help="audio files (voice notes…) -> transcripts by the stt poste via walter-llm")
    tr.add_argument("files", nargs="+")
    tr.add_argument("--source", default="walter-router", help="caller name recorded by walter-llm")
    ak = sub.add_parser("ask", help="the decision model for a quick choice: question + options -> choice, confidence")
    ak.add_argument("question")
    ak.add_argument("--option", action="append", required=True, metavar="NAME=MEANING")
    ak.add_argument("--context")
    cl = sub.add_parser("classify", help="intent only, by the decision model (task, video role, level, unrestricted)")
    cl.add_argument("request")
    cl.add_argument("--context", help="one line on what the conversation was about before this request")
    o = sub.add_parser("dossier", help="the task's pre-computed dossier (what the router reads)")
    o.add_argument("task")
    q = sub.add_parser("plans", help="the owner's plans (subscriptions): list | set ID [--price …] | retire ID")
    q.add_argument("action", choices=["list", "set", "retire"])
    q.add_argument("sub_id", nargs="?")
    q.add_argument("--vendor"); q.add_argument("--plan"); q.add_argument("--price", type=float, dest="price_usd_month")
    q.add_argument("--execution"); q.add_argument("--route-provider", dest="route_provider")
    q.add_argument("--models", help="comma-separated model ids included in the plan"); q.add_argument("--note")
    q.add_argument("--since", help="start date (YYYY-MM-DD)"); q.add_argument("--until", help="end date of an offer (YYYY-MM-DD)")
    q.add_argument("--list-price", type=float, dest="list_price_usd_month", help="catalogue price when the plan is a free offer")
    q.add_argument("--why", default="déclaré par le propriétaire")
    q = sub.add_parser("research", help="run research now: one or more categories (text image video audio memory "
                                        "decision prices hosts plans | all), or --source KIND; --list shows them")
    q.add_argument("categories", nargs="*", help="research categories (default: all)")
    q.add_argument("--source", action="append", dest="sources", help="source kind instead, e.g. aa_eval, arena (repeatable)")
    q.add_argument("--list", action="store_true", help="categories with what each reads")
    q.add_argument("--analyse", action="store_true", help="then recompute the choices and republish the page (no message)")
    q.add_argument("--no-web", action="store_true", help="plans: skip the web research agent (meters, mails, cost price only)")
    q.add_argument("--no-notify", action="store_true", help="plans: record news and proposals without sending them")
    bf = sub.add_parser("brief", help="what an agent must know to use the router (tools, levels, specialities, "
                                      "generation, constraints) — no model names")
    bf.add_argument("--json", action="store_true", help="versioned stable note for walter-context and harnesses")
    bf.add_argument("--write", action="store_true", help="write it to the instance's state/router/brief.md and "
                                                        "re-render the agent profiles (walter-soul) when it changed")
    wb = sub.add_parser("web", help="conversational web service (walter_web): JSON spec on stdin (service, message, "
                                    "model, files = local paths, conversation, request_id, timeout_s) -> JSON reply, "
                                    "produced files as local paths")
    wb.add_argument("--message", help="instead of a JSON spec: just this message, default service, default model")
    sub.add_parser("web-commands", help="chat commands of the web services ({command: service}), for the Telegram door")
    sub.add_parser("instance-env", help="shell assignments of the instance bindings used by the cycle and the trigger")
    sub.add_parser("schema", help="versioned public tool parameter reference (JSON, no model call)")
    doc = sub.add_parser("docs", help="generate or check reference documentation against source and the models schema")
    mode = doc.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate reference files; reads DB metadata only")
    mode.add_argument("--check", action="store_true", help="exit nonzero on stale or incomplete reference docs")
    doc.add_argument("--offline", action="store_true", help="check against the committed database metadata snapshot")
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    if args.cmd == "schema":
        from walter_router.serve.api import schema
        print(json.dumps(schema(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "docs":
        from walter_router.documentation import maintain
        out = maintain(write=args.write, offline=args.offline)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] else 1
    if args.cmd == "plans":
        from walter_router.plan import declared
        if args.action == "list":
            print(json.dumps(declared.read().get("subscriptions", []), ensure_ascii=False, indent=1))
            return 0
        if not args.sub_id:
            print(json.dumps({"error": "plan id required"}))
            return 1
        if args.action == "retire":
            out = declared.retire(args.sub_id, args.why)
        else:
            fields = {k: getattr(args, k) for k in ("vendor", "plan", "price_usd_month", "execution", "route_provider", "note",
                                                    "since", "until", "list_price_usd_month")}
            if args.models:
                fields["models"] = [m.strip() for m in args.models.split(",") if m.strip()]
            out = declared.upsert(args.sub_id, fields, args.why)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "button" and args.data.startswith("wr:b:"):   # a decision-bench label (owner's blind answer)
        from walter_router.eval import decision_bench
        print(json.dumps(decision_bench.button(args.data), ensure_ascii=False))
        return 0
    if args.cmd == "decision-bench":
        from walter_router.eval import decision_bench as bench
        if args.action in ("label", "status", "report"):
            out = {"label": bench.send_next, "status": bench.status, "report": bench.report}[args.action]()
        else:
            with db.connect() as conn:
                out = bench.build(conn) if args.action == "build" else bench.run(
                    conn, tuple(args.models.split(",")) if args.models else bench.MODELS, args.samples)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "research":
        from walter_router.research import run as research_run
        return research_run.main(args)
    if args.cmd == "instance-env":
        return _instance_env()
    if args.cmd == "web":
        from walter_router.serve import web
        out = web.converse({"message": args.message} if args.message else json.load(sys.stdin))
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if out.get("ok") else 1
    if args.cmd == "web-commands":
        from walter_router.serve import web
        print(json.dumps(web.commands(), ensure_ascii=False))
        return 0
    if args.cmd == "brief":
        from walter_router.serve import brief
        with db.connect() as conn:
            if not args.write:
                print(json.dumps(brief.document(conn), ensure_ascii=False) if args.json else brief.text(conn))
                return 0
            changed = brief.write(conn)
        if changed:   # the Codex / DSH profiles include the module layer that carries it: walter-context
            import shutil  # republishes it and re-renders the profiles (walter-soul) when the layer changed
            import subprocess
            if shutil.which("walter-context"):
                subprocess.run(["walter-context", "capability", "all", "--write"], capture_output=True, timeout=180)
            elif shutil.which("walter-soul"):
                subprocess.run(["walter-soul", "sync"], capture_output=True, timeout=120)
        print(json.dumps({"written": str(instance.state_file("brief.md")), "changed": changed}))
        return 0
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
    elif args.cmd == "transcribe":
        from walter_router.serve import oneshot
        out = {"results": [oneshot.transcribe(f, args.source) for f in args.files]}
    else:
        with db.connect() as conn:
            if args.cmd == "pick":
                out = with_execution(conn, choose.pick(conn, args.task, args.level, args.role, args.require))
                out = agent_view.view(out) if args.agent else out
            elif args.cmd == "prefer":
                out = choose.set_preference(conn, args.task, args.objective, args.pin, args.provider, args.note,
                                            args.role, args.watch)
            elif args.cmd == "decide":
                out = with_execution(conn, knowledge.decide(conn, args.task, args.intent, args.level))
            elif args.cmd == "route":
                out = named.named(conn, args.model, args.provider, args.task) if args.model else \
                    route(conn, args.request, args.task, args.level, args.context)
                out = agent_view.view(out) if args.agent else out
            elif args.cmd == "run":
                spec = json.load(sys.stdin)
                out = run_job.decide(conn, spec) if args.dry_run else run_job.run(conn, spec)
            elif args.cmd == "ask":
                opts = dict(o.split("=", 1) for o in args.option if "=" in o)
                out = intent.ask(conn, args.question, opts, args.context)
            elif args.cmd == "classify":
                out = intent.classify(conn, args.request, context=args.context)
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
            elif args.cmd == "analyze":
                from walter_router.research.agent import run as agent_run
                out = agent_run.run(conn)
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
                # internal = a poste the modules call (memory extraction, compression, voice…): never an intent class
                out = list(conn.execute("select task, label, interface, internal from models.tasks where interface <> 'decisions' "
                                        "order by interface, task"))
            elif args.cmd == "dossier":
                out = dossier.latest(conn, args.task)
            elif args.cmd == "declare":
                out = knowledge.declare(conn)
            elif args.cmd == "alerts":
                rows = conn.execute("select * from models.alerts order by alert_id").fetchall() if args.all else alerts.pending(conn)
                out = rows
            else:
                if args.cmd == "button":
                    parts = args.data.split(":", 3)
                    if len(parts) < 3 or parts[0] != "wr" or parts[1] not in ("a", "d") or not parts[2].isdigit():
                        raise SystemExit(json.dumps({"ok": False, "toast": "Bouton inconnu"}))
                    args.alert_id, args.decision = int(parts[2]), "adopted" if parts[1] == "a" else "dismissed"
                    args.note, args.role = None, (parts[3] if len(parts) > 3 else None)
                out = alerts.verdict(conn, args.alert_id, args.decision, args.note, args.role)
                if args.cmd == "button":
                    out = {"ok": True, "toast": "Enregistré : " + ("adopté" if args.decision == "adopted" else "ignoré"),
                           "drop": [f"wr:a:{args.alert_id}", f"wr:d:{args.alert_id}"], "verdict": out}
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
