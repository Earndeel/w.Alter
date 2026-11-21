"""The Router guardian's « advice » mission (owner, 2026-11-20: « le router doit avoir un vrai agent intelligent qui
s'occupe de comprendre les tenants et les aboutissants » ; 2026-11-21: « cet agent est supposé être le guardian »).

The guardian has one identity (`guardian-router`) and two missions: repair what breaks (run.py / repair.py, on an
incident) and advise (this file). Its standing instructions are a readable file, `guardian/advice-brief.md`; the
owner's own rules for it live in the instance (`config/router/guardian-rules.md`) and come last in the brief.

The cycle's rules (tiers.py, alerts.py) see one thing at a time; the guardian reads the whole picture after each cycle
and after each choice of the owner — declared tiers, their quota substitutes, padlocks, the frontier with measured and
estimated subscription costs, what changed, what the owner already accepted or refused — and works out the
consequences (a substitute left behind by a new tier, an estimate a measure contradicts, a tier that no longer fits
the owner's rules…). It is one Walter Engine delegation (caller `guardian-router`, poste general/L3) that
investigates read-only and ends with a JSON verdict. Its proposals become 'advice' alerts sent on Telegram with
buttons; adopting one applies exactly one whitelisted action (OPS) through the Router's usual writers. It never
changes anything by itself: the owner decides (CLAUDE.md: Telegram proposals, never an automatic switch).

One agent, not two (owner, 2026-11-20): at the 48 h cycle (step 2, `walter-router analyze`) it also does what the
former cycle analyst did — sources and providers, name links checked on the web (applied by the Router through the
validated `aliases_admin.add`, the only thing applied without the owner: a name, never a model choice) and the cycle
report `analysis-<day>.md`. Its time is bounded: the facts are precomputed in the state, the brief caps the checks and
gives the deadline, and the engine tells a delegation to conclude before its budget cuts it (the first run, 2026-11-20,
spent 25 min reading the Router's code and was cancelled without a verdict).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from walter_router import instance, paths

ENGINE_URL = os.environ.get("WALTER_ENGINE_API_URL", "http://127.0.0.1:8895")
CALLER = "guardian-router"             # the guardian's one identity (policy « guardian- » = maintenance)
TASK, LEVEL = "general", "L3"           # the owner's top text tier: understanding consequences is its job
BUDGET = 1100                           # seconds per run; fits the cycle's `timeout 1300 walter-router analyze`
MAX_CHECKS = 12                         # commands or web searches before concluding
MAX_PROPOSALS = 3
OWNER_DELAY = 90                        # after an owner's click: let a burst of clicks land before reading the state
UNIT = "walter-router-guardian-advice"
OPS = ("set_quota_fallback", "set_level", "set_preference", "set_lock", "note")
LEVELS = ("L1", "L2", "L3")


# ---- the picture ---------------------------------------------------------------------------------------------------

def _pin(model_id, variant) -> str | None:
    return f"{model_id}/{variant}" if model_id and variant else model_id


def _aa(conn, model_id: str, variant: str) -> dict | None:
    r = conn.execute("""select b.score, b.cost from models.benchmarks b join models.latest_snapshots l using (snapshot_id)
                        where b.benchmark = 'aa_intelligence' and b.model_id = %s and b.variant = %s
                        order by b.score desc limit 1""", (model_id, variant or "")).fetchone()
    return dict(r) if r else None


def _routes(conn, pin: str | None) -> list[str]:
    if not pin:
        return []
    from walter_router.serve import execution
    mid, _, var = pin.partition("/")
    try:
        return [f'{r["provider"]}:{r.get("access")}' for r in execution.routes(conn, mid, var)]
    except Exception:  # noqa: BLE001 — unknown model: no route, which is the point to report
        return []


def state(conn, trigger: str = "manual", extra: dict | None = None) -> dict:
    """Everything the guardian needs to advise, compact and in one snapshot of the index."""
    from walter_router.analysis import changes, knowledge
    from walter_router.analysis import select as sel
    levels = (knowledge.load().get("levels") or {}).get("general") or {}
    declared = {}
    for lv in LEVELS:
        d = levels.get(lv) or {}
        entry = {k: d.get(k) for k in ("pin", "provider", "fallback", "when_quota_spent", "evidence") if d.get(k)}
        for key in ("pin", "fallback", "when_quota_spent"):
            if d.get(key):
                mid, _, var = d[key].partition("/")
                entry[f"{key}_now"] = {"aa": _aa(conn, mid, var), "routes": _routes(conn, d[key])}
        declared[lv] = entry
    run = conn.execute("select run_id from models.latest_run").fetchone()
    tiers, frontier = [], []
    if run:
        for r in conn.execute("""select level, rank, model_id, variant, quality, real_cost, reasons from models.selection
                                 where run_id = %s and task = 'general' and level in ('L1', 'L2', 'L3', 'frontier')
                                 order by level, rank""", (run["run_id"],)):
            rs = r["reasons"] or {}
            sub = rs.get("subscription_cost") or {}
            row = {"pin": _pin(r["model_id"], r["variant"]), "score": r["quality"],
                   "cost_per_task": r["real_cost"] and round(r["real_cost"], 4),
                   "via": sub.get("provider") if sub.get("cost") == r["real_cost"] else (rs.get("provider") or "paid"),
                   **({"estimated_from": sub["estimated_from"]} if sub.get("estimated_from") else {})}
            if r["level"] == "frontier":
                frontier.append(row)
            else:
                tiers.append({"level": r["level"], **row, "role": rs.get("role"), "hold": rs.get("hold"),
                              "method_pick": rs.get("method_pick"), "quota_rule": rs.get("quota_rule")})
    subs = sel.load_subscription_costs(conn)
    prefs = [{"task": r["task"], "role": r["role"], "pin": _pin(r["pinned_model_id"], r["pinned_variant"]),
              "provider": r["pinned_provider"], "locked": r["locked"]}
             for r in conn.execute("""select task, role, pinned_model_id, pinned_variant, pinned_provider, locked
                                      from models.preferences where pinned_model_id is not null order by task, role""")]
    chg = changes.events(conn)
    recent = [dict(r) for r in conn.execute(
        """select kind, task, role, subject, status, verdict_note, evidence->'why' as why,
                  evidence->>'title_fr' as title, to_char(last_seen, 'YYYY-MM-DD') as seen
           from models.alerts where kind in ('tier', 'pareto', 'advice', 'challenger', 'new_best', 'nerf')
             and last_seen > now() - interval '30 days' and status <> 'baseline'
           order by last_seen desc limit 60""")]
    try:
        rules = (paths.ROOT / "docs" / "TIERS.md").read_text()
    except OSError:
        rules = ""
    cycle = _cycle_facts(conn) if trigger == "cycle" else None
    return {**({"cycle": cycle} if cycle else {}),"now": datetime.now(timezone.utc).isoformat(timespec="minutes"), "trigger": trigger, "detail": extra or {},
            "declared_text_tiers": declared, "method_tiers_last_cycle": tiers, "text_frontier": frontier[:30],
            "subscription_cost_ratios": [{"route_provider": p, "model_id": m, "ratio": v.get("ratio"),
                                          "source": v.get("source"), "estimated_from": v.get("estimated_from")}
                                         for (p, m), v in sorted(subs.items())],
            "preferences": prefs,
            "changes_since_previous_cycle": {"new": sorted(chg["new"])[:40], "nerf": chg["nerf"],
                                             "price_drop": chg["price_drop"], "rebased": chg["rebased"]},
            "recent_alerts_and_owner_answers": recent, "tier_rules": rules}


def _cycle_facts(conn) -> dict:
    """What the former cycle analyst read: sources, providers, name candidates, price moves, health, existing links."""
    from walter_router.analysis import aliases_admin
    from walter_router.health import health
    from walter_router.research.agent import review
    d = review.digest(conn)
    d.pop("tiers", None)                                   # the tiers are already in the state, with more detail
    try:
        h = health()
    except Exception as exc:  # noqa: BLE001 — the health check is a fact among others
        h = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"review": d, "health": h,
            "name_links_already_made": {k: v.get("model_id") for k, v in (aliases_admin.listing() or {}).items()}}


BRIEF_FILE = Path(__file__).with_name("advice-brief.md")
CYCLE_SECTION = "\n## Au cycle de 48 h\n"


def owner_rules() -> list[str]:
    """The owner's own rules for the guardian (instance file config/router/guardian-rules.md, lines « - … »)."""
    try:
        text = instance.config_path("guardian-rules.md").read_text()
    except OSError:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("- ") and len(ln.strip()) > 2]


def brief(st: dict, budget: int = BUDGET, start: float | None = None) -> str:
    """The guardian's standing instructions (advice-brief.md, readable and editable), the owner's rules, the state."""
    text = BRIEF_FILE.read_text().split("\n---\n", 1)[-1]          # the file's own header is for humans
    main, _, cycle = text.partition(CYCLE_SECTION)
    owner = instance.owner()
    deadline = datetime.fromtimestamp((time.time() if start is None else start) + budget * 0.75, timezone.utc)
    out = main.strip() + ("\n\n" + cycle.strip() if st.get("cycle") else "")
    rules = owner_rules()
    if rules:
        out += f"\n\n## Règles de {owner} pour toi (elles priment sur ce qui précède)\n" + "\n".join(rules)
    for key, value in {"owner": owner, "trigger": st.get("trigger"), "minutes": round(budget * 0.75 / 60),
                       "deadline": deadline.strftime("%H:%M"), "checks": MAX_CHECKS, "max": MAX_PROPOSALS}.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out + "\n\n## État\n```json\n" + json.dumps(st, ensure_ascii=False, separators=(",", ":"), default=str) + "\n```"


def verdict_of(output: str) -> dict | None:
    """The agent's closing JSON: the last object carrying `proposals`."""
    decoder = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"\{", output or ""))):
        try:
            obj, _ = decoder.raw_decode(output[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("proposals"), list):
            return obj
    return None


# ---- actions --------------------------------------------------------------------------------------------------------

def _callable(conn, task: str, pin: str) -> bool:
    from walter_router.serve.choose import routes_for
    t = conn.execute("select interface, modes from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        return False
    mid, _, var = pin.partition("/")
    if t["interface"] == "chat" and not _aa(conn, mid, var) and var:
        return False                                      # a reasoning level the index does not know
    return bool(routes_for(conn, mid, t["interface"], t["modes"] or None).get("callable"))


def validate(conn, action: dict) -> str | None:
    """None when the action can be applied as is, else why not."""
    if not isinstance(action, dict) or action.get("op") not in OPS:
        return "action inconnue"
    op = action["op"]
    if op == "note":
        return None
    if op in ("set_quota_fallback", "set_level"):
        from walter_router.analysis import knowledge
        if action.get("level") not in LEVELS:
            return "niveau inconnu"
        lv = ((knowledge.load().get("levels") or {}).get("general") or {}).get(action["level"]) or {}
        for key in ("pin", "when_quota_spent"):
            pin = action.get(key)
            if key == "pin" or pin:
                if not isinstance(pin, str) or "/" not in pin:
                    return f"{key} doit être model_id/variant"
                if not _callable(conn, "general", pin):
                    return f"{pin} n'a pas de route"
        if op == "set_quota_fallback" and action["pin"] == lv.get("pin"):
            return "le relais serait le modèle du niveau lui-même"
        if op == "set_quota_fallback" and action["pin"] == lv.get("when_quota_spent") == lv.get("fallback"):
            return "déjà en place"
        if op == "set_level" and action["pin"] == lv.get("pin"):
            return "déjà en place"
        return None
    task, role = action.get("task"), action.get("role") or "default"
    if not conn.execute("select 1 from models.tasks where task = %s", (task,)).fetchone():
        return "tâche inconnue"
    if op == "set_lock":
        return None if isinstance(action.get("locked"), bool) else "locked doit être true ou false"
    pin = action.get("pin")
    if not isinstance(pin, str) or not pin:
        return "pin manquant"
    return None if _callable(conn, task, pin) else f"{pin} n'a pas de route"


def subject(action: dict, title: str = "") -> str:
    """One proposal = one action: the same action proposed twice is the same alert (a refusal stays a refusal). A note
    has no action to tell it apart: its title does (2026-11-20, two notes of one run collapsed into one alert)."""
    keys = [k for k in ("op", "level", "task", "role", "pin", "provider", "when_quota_spent", "locked") if k in action]
    head = ":".join(str(action.get(k)) for k in keys)
    if action.get("op") == "note":
        head += ":" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:120]
    return head[:300]


def apply(conn, action: dict, note: str) -> dict:
    """The owner adopted the guardian's advice: one action through the Router's usual writers."""
    err = validate(conn, action)
    if err and err != "déjà en place":
        raise ValueError(err)
    op = action["op"]
    if op == "note" or err:
        return {"applied": False, "op": op, **({"why": err} if err else {})}
    from walter_router.analysis import alerts, knowledge
    from walter_router.serve.choose import set_preference
    if op == "set_quota_fallback":
        lv = knowledge.load()["levels"]["general"][action["level"]]
        knowledge.set_level("general", action["level"], lv["pin"], why=note, provider=lv.get("provider"),
                            fallback=action["pin"], when_quota_spent=action["pin"])
        return {"applied": True, "op": op, "level": action["level"], "when_quota_spent": action["pin"]}
    if op == "set_level":
        spent = action.get("when_quota_spent")
        knowledge.set_level("general", action["level"], action["pin"], why=note, provider=action.get("provider"),
                            **({"when_quota_spent": spent, "fallback": spent} if spent else {}))
        set_preference(conn, "general", pin=action["pin"], provider=action.get("provider"), role=action["level"],
                       watch="dominance", note=note)
        return {"applied": True, "op": op, "level": action["level"], "pin": action["pin"]}
    if op == "set_preference":
        set_preference(conn, action["task"], pin=action["pin"], provider=action.get("provider"),
                       role=action.get("role") or "default", note=note)
        return {"applied": True, "op": op, "task": action["task"], "pin": action["pin"]}
    out = alerts.set_lock(conn, action["task"], action.get("role"), action["locked"])
    return {"applied": True, "op": op, **out}


def record(conn, verdict: dict, run: dict) -> list[dict]:
    """The guardian's proposals as 'advice' alerts (open → sent on Telegram); refused actions are kept in the run log."""
    from walter_router.analysis import alerts
    kept = []
    for p in (verdict.get("proposals") or [])[:MAX_PROPOSALS]:
        if not isinstance(p, dict):
            continue
        action = p.get("action") or {"op": "note"}
        err = validate(conn, action)
        if err:
            kept.append({"title_fr": p.get("title_fr"), "refused": err, "action": action})
            continue
        ev = {"title_fr": str(p.get("title_fr") or "")[:200], "why_fr": str(p.get("why_fr") or "")[:900],
              "consequences_fr": str(p.get("consequences_fr") or "")[:600], "action": action,
              "trigger": run.get("trigger"), "run_at": run.get("at")}
        new = alerts.record(conn, "advice", action.get("task") or "general", subject(action, ev["title_fr"]), ev, "open",
                            action.get("level") or action.get("role") or "")
        kept.append({"title_fr": ev["title_fr"], "action": action, "new": new})
    return kept


# ---- running ---------------------------------------------------------------------------------------------------------

def _engine_token() -> str:
    root = instance._walter("path")
    if not root:
        raise RuntimeError("no active Walter instance")
    return (Path(root) / "bootstrap" / "engine" / "api.token").read_text().strip()


def delegate(goal: str, key: str, budget: int = BUDGET) -> dict:
    """One Walter Engine delegation (Engine API, the declared door to the runtime)."""
    body = {"version": 1, "op": "delegate", "caller": CALLER,
            "delegation": {"version": 1, "goal": goal, "task": TASK, "level": LEVEL, "budget_seconds": budget,
                           "idempotency_key": key, "parent": {"depth": 0}}}
    req = Request(ENGINE_URL.rstrip("/") + "/v1", data=json.dumps(body).encode(),
                  headers={"Authorization": "Bearer " + _engine_token(), "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=budget + 120) as r:
            out = json.load(r)
    except Exception as exc:  # noqa: BLE001 — engine down: a failed run, said as such
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    res = out.get("result") or out
    return {"ok": bool(res.get("ok")), "output": res.get("output") or "", "status": res.get("status"),
            "reason": res.get("reason"), "error": res.get("error"), "tools": len(res.get("tools") or [])}


def _log(entry: dict) -> None:
    try:
        f = instance.state_file("guardian/advice-runs.jsonl")
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 — the log is a trace, never a reason to fail the run
        pass


def cycle_report(conn, v: dict | None, ran: dict, *, add=None, log_dir: Path | None = None,
                 now: datetime | None = None) -> dict:
    """The cycle's part of the verdict: name links applied through the validated add, report written."""
    from walter_router.analysis import aliases_admin
    from walter_router.research.agent import run as names
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    aliases = [a for a in ((v or {}).get("aliases") or []) if isinstance(a, dict)
               and all(isinstance(a.get(k), str) and a.get(k) for k in ("key", "model_id", "reason"))]
    added, refused = names.apply(conn, aliases, add or aliases_admin.add) if v else ([], [])
    answer = None
    if v:
        props = [f"- {k.get('title_fr')}" + (f" (refusée : {k['refused']})" if k.get("refused") else "")
                 for k in v.get("_kept") or []]
        answer = {"report": (str(v.get("report_fr") or v.get("summary_fr") or "").strip()
                             + ("\n\n## Conseils envoyés à " + instance.owner() + "\n" + "\n".join(props) if props else ""))}
    raw = None if not ran.get("output") and not ran.get("ok") else ran.get("output")
    path = Path(log_dir or instance.host_path("log_dir")) / f"analysis-{day}.md"
    path.write_text(names.report_text(day, answer, added, refused, raw))
    return {"report": str(path), "added": [a["added"] for a in added], "refused": len(refused)}


def run(trigger: str = "manual", extra: dict | None = None, dry_run: bool = False, notify: bool = True,
        budget: int = BUDGET) -> dict:
    """One advice pass of the guardian. trigger 'cycle' = step 2 of the 48 h cycle (names, sources, report; `notify=False`: step 3's
    refresh sends the Telegram message); 'owner' = after an owner's choice (consequences only)."""
    from walter_router.analysis import telegram
    from walter_router.store import db
    started = time.time()
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        st = state(conn, trigger, extra)
    goal = brief(st, budget, started)
    if dry_run:
        return {"trigger": trigger, "brief_chars": len(goal), "state": st}
    ran = delegate(goal, f"router-guardian-advice-{trigger}-{int(started)}"[:200], budget)
    v = verdict_of(ran.get("output") or "")
    entry = {"at": at, "trigger": trigger, "detail": extra, "seconds": round(time.time() - started),
             "engine": {k: ran.get(k) for k in ("ok", "status", "reason", "error", "tools")}}
    with db.connect() as conn:
        kept = record(conn, v, {"trigger": trigger, "at": at}) if v else []
        if v:
            v["_kept"] = kept
        if trigger == "cycle":
            entry["cycle"] = cycle_report(conn, v, ran)
        sent = telegram.notify(conn) if notify and any(k.get("new") for k in kept) else {"sent": 0}
        conn.commit()
    if not v:
        _log({**entry, "verdict": None, "tail": (ran.get("output") or "")[-600:]})
        return {**entry, "ok": False, "verdict": None}
    entry.update(ok=True, summary_fr=v.get("summary_fr"), proposals=kept, notify=sent)
    _log(entry)
    return entry


def launch(trigger: str, extra: dict | None = None, delay: int = 0) -> bool:
    """Start a run in its own transient unit (the cycle or the Telegram click never waits for it). One at a time."""
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("WALTER_ROUTER_ADVISOR") == "off":
        return False
    if subprocess.run(["systemctl", "is-active", "--quiet", UNIT]).returncode == 0:
        return False
    cmd = [str(paths.ROOT / "bin" / "walter-router-guardian"), "advise", "run", "--trigger", trigger]
    if extra:
        cmd += ["--detail", json.dumps(extra, ensure_ascii=False, default=str)[:2000]]
    if delay:
        cmd = ["sh", "-c", f"sleep {int(delay)}; exec \"$@\"", "sh", *cmd]
    r = subprocess.run(["systemd-run", "--unit", UNIT, "--collect", "--quiet",
                        f"--property=RuntimeMaxSec={BUDGET + 600}", *cmd], capture_output=True, text=True, timeout=30)
    return r.returncode == 0
