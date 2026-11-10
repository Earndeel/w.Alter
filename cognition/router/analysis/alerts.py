"""Alerts: a pinned favourite overtaken, unranked new releases, stale sources — and their Telegram notification."""
from __future__ import annotations

import json
import subprocess

from walter_router.analysis import catalog
from walter_router.analysis import changes
from walter_router import instance
from walter_router.analysis import select as sel

HERMES = instance.hermes_bin()
UNRANKED_DAYS = 30
STALE_HOURS = {"aa": 60, "aa_eval": 60, "aa_decision": 60, "mm": 60, "da": 60, "arena": 60, "bridgebench": 60, "aa_stt": 60,
               "agentset": 60, "mteb": 60, "openrouter": 60, "kie": 60, "codex": 60, "hermes_providers": 60,
               "declared": 24 * 365}  # 48 h cycle + 12 h margin (aa_stt / agentset / mteb were at the 48 h default)


def record(conn, kind: str, task: str, subject: str, evidence: dict, status: str, role: str = "") -> bool:
    """Insert or refresh an alert; returns True when it is new. Verdicts and statuses are never overwritten."""
    row = conn.execute("""insert into models.alerts (kind, task, role, subject, evidence, status)
                          values (%s, %s, %s, %s, %s::jsonb, %s)
                          on conflict (kind, task, role, subject) do update set last_seen = now(), evidence = excluded.evidence
                          returning (xmax = 0) as inserted""",
                       (kind, task, role, subject, json.dumps(evidence, default=str), status)).fetchone()
    return bool(row["inserted"])


def _unit_cost(offers: list[dict], interface: str, modes: list[str] | None = None) -> float | None:
    if interface == "chat":
        paid = sel.chat_route(offers, None, modes)["paid"]
        return paid["blended_1m"] if paid else None
    paid = sel.media_route(offers, interface, modes)["paid"]
    return paid["cost"] if paid else None


def _board_rows(conn, snaps: dict, benchmark: str, bench_task: str) -> list[dict]:
    sid = sel.board_snapshot(conn, snaps, benchmark, bench_task)
    if sid is None:
        return []
    return list(conn.execute("""select model_id, variant, display_name, score, score_unit, extra from models.benchmarks
                               where snapshot_id = %s and benchmark = %s and task = %s""", (sid, benchmark, bench_task)))


TOP_N = 3


def _order(rows: list[dict]) -> list[str]:
    """Distinct models of a board, best first (variants of one model count once)."""
    seen: list[str] = []
    for r in sorted(rows, key=lambda r: -r["score"]):
        if r["model_id"] not in seen:
            seen.append(r["model_id"])
    return seen


def new_best(conn, run_id: int, chg: dict | None = None) -> list[str]:
    """A new #1 for a specialised task is only PROPOSED (2026-10-16: « je dois toujours appuyer sur le
    bouton pour confirmer les changements de modèle »): the model in use is pinned at once, the message brings the
    facts, and only their « Passer à … » button switches."""
    prev = conn.execute("""select run_id from models.runs where status = 'ok' and run_id < %s
                           order by run_id desc limit 1""", (run_id,)).fetchone()
    if not prev:
        return []
    created = []
    for r in conn.execute("""select n.task, t.label, t.interface, n.model_id as new_id, n.display_name, n.quality,
                                    o.model_id as old_id, o.display_name as old_name
                             from models.selection n join models.selection o
                               on o.run_id = %s and o.task = n.task and o.level = 'best' and o.rank = 1
                             join models.tasks t on t.task = n.task
                             where n.run_id = %s and n.level = 'best' and n.rank = 1 and n.task <> 'general'
                               and n.model_id <> o.model_id
                               and not exists (select 1 from models.preferences p where p.task = n.task
                                               and p.pinned_model_id is not null)""", (prev["run_id"], run_id)):
        old_q = conn.execute("""select quality from models.selection where run_id = %s and task = %s and level = 'best'
                                and model_id = %s""", (run_id, r["task"], r["old_id"])).fetchone()
        if not old_q:   # only the #1 is saved for specialised tasks: score the previous one on the same composite
            from walter_router.analysis.scoring import composite
            prev_c = next((c["composite"] for c in composite(conn, r["task"]) if c["model_id"] == r["old_id"]), None)
            old_q = {"quality": prev_c} if prev_c is not None else None
        if old_q and r["quality"] is not None and old_q["quality"] >= r["quality"]:
            continue  # reshuffle by tie-break, not a better model (an unranked newer version is always proposed)
        chg = chg or changes.events(conn)
        why = changes.changed(chg, r["new_id"]) + [f'{r["old_id"]} dégradé' for _ in chg["nerf"].get(r["old_id"], [])[:1]]
        ev = {"task_label": r["label"], "interface": r["interface"], "name": r["display_name"], "score": r["quality"],
              "previous": r["old_id"], "previous_name": r["old_name"], "previous_score": old_q and old_q["quality"],
              "why": why}
        from walter_router.serve.choose import set_preference
        set_preference(conn, r["task"], pin=r["old_id"], watch="quality",
                       note=f'Gardé en attendant la décision de {instance.owner()} (proposition : {r["new_id"]}).')
        if record(conn, "new_best", r["task"], r["new_id"], ev, "open" if why else "baseline") and why:
            created.append(f'{r["task"]}:{r["new_id"]}')
    return created


def top3(conn, status_for_new: str | None = None) -> list[str]:
    """A model entering the top 3 of a leaderboard in a domain the owner watches (interfaces they have preferences on).
    The first computation records the current podiums as 'baseline'."""
    if status_for_new is None:
        first = conn.execute("select not exists (select 1 from models.alerts where kind = 'top3') as f").fetchone()["f"]
        status_for_new = "baseline" if first else "open"
    snaps = sel.latest_snapshots(conn)
    watched = _watched_interfaces(conn)
    podium: dict[tuple[str, str], dict] = {}
    for tb in conn.execute("""select tb.*, t.interface from models.task_benchmarks tb join models.tasks t using (task)
                              order by tb.benchmark, tb.bench_task""").fetchall():
        if tb["interface"] not in watched:
            continue
        rows = _board_rows(conn, snaps, tb["benchmark"], tb["bench_task"])
        board = f'{catalog.BOARDS.get(tb["benchmark"], tb["benchmark"])} {tb["bench_task"]}'
        for rank, model_id in enumerate(_order(rows)[:TOP_N], 1):
            ev = podium.setdefault((tb["interface"], model_id), {"interface": tb["interface"], "boards": {}})
            ev["boards"][board] = {"rank": rank, "score": max(r["score"] for r in rows if r["model_id"] == model_id)}
    created = []
    for (interface, model_id), ev in podium.items():
        if record(conn, "top3", interface, model_id, ev, status_for_new):
            created.append(f"{interface}:{model_id}")
    return created


# boards whose score is a "higher = better" transform of a lower-is-better measure: (unit marker, raw key, label)
RAW_MEASURES = (("latency", "latency_ms", "ms"), ("WER", "wer_pct", "% WER"))


def _raw_measure(theirs: dict, mine: dict) -> dict:
    """{'raw': [challenger, pinned, unit]} for a latency / WER board, read as measured."""
    for marker, key, unit in RAW_MEASURES:
        if marker in (theirs.get("unit") or "") and theirs.get(key) is not None:
            return {"raw": [theirs[key], mine.get(key), unit]}
    return {}


def challengers(conn, status_for_new: str = "open", only_task: str | None = None,
                only_role: str | None = None, chg: dict | None = None) -> list[str]:
    """Models that overtake one of the owner's pinned favourites on any leaderboard of that task
    (models.task_benchmarks: AA, Design Arena, Arena.ai). One alert per challenger model, listing every board.

    watch = quality   -> any model scoring higher;
    watch = dominance -> scoring higher AND no more expensive per unit (ratio / budget picks);
    watch = none      -> never.
    """
    snaps = sel.latest_snapshots(conn)
    offers = sel.load_offers(conn, snaps)
    chg = chg or changes.events(conn)  # only a CHANGE (new / cheaper challenger, nerfed favourite) is news
    created = []
    for p in conn.execute("""select p.*, t.label, t.interface, t.modes from models.preferences p
                             join models.tasks t using (task) where p.pinned_model_id is not null and p.watch <> 'none'
                             and (%s::text is null or p.task = %s) and (%s::text is null or p.role = %s)""",
                          (only_task, only_task, only_role, only_role)).fetchall():
        boards = conn.execute("""select benchmark, bench_task from models.task_benchmarks where task = %s
                                 order by is_primary desc, benchmark""", (p["task"],)).fetchall()
        if not boards:
            continue
        ref_cost = _unit_cost(offers.get(p["pinned_model_id"], []), p["interface"], p["modes"])
        if p["watch"] == "dominance" and ref_cost is None:
            continue  # no comparable price for the favourite: dominance cannot be established
        found: dict[str, dict] = {}
        measured = False
        costs: dict[str, float | None] = {}

        def cost_of(model_id: str) -> float | None:
            if model_id not in costs:
                costs[model_id] = _unit_cost(offers.get(model_id, []), p["interface"], p["modes"])
            return costs[model_id]

        for b in boards:
            rows = _board_rows(conn, snaps, b["benchmark"], b["bench_task"])
            # Relevance (2026-10-02): only a challenger in the board's top 3 is worth a message —
            # top 3 overall for a quality favourite, top 3 among models no dearer than the favourite for a
            # ratio / budget favourite.
            pool = rows if p["watch"] == "quality" else \
                [r for r in rows if cost_of(r["model_id"]) is not None and cost_of(r["model_id"]) <= ref_cost]
            podium = _order(pool)[:TOP_N]
            same = [r for r in rows if r["model_id"] == p["pinned_model_id"]]
            mine = [r for r in same if r["variant"] == p["pinned_variant"]] or same
            if not mine:
                continue
            measured = True
            ref = max(r["score"] for r in mine)
            board = f'{catalog.BOARDS.get(b["benchmark"], b["benchmark"])} {b["bench_task"]}'
            for r in rows:
                if r["model_id"] == p["pinned_model_id"] or r["score"] <= ref or r["model_id"] not in podium:
                    continue
                cost = cost_of(r["model_id"])
                ev = found.setdefault(r["model_id"], {
                    "task_label": p["label"], "role": p["role"], "watch": p["watch"], "pinned": p["pinned_model_id"],
                    "pinned_unit_cost": ref_cost, "unit_cost": cost, "boards": {},
                    "callable_via": sorted({o["provider"] for o in offers.get(r["model_id"], [])})})
                prev = ev["boards"].get(board)
                if prev is None or r["score"] - ref > prev["delta"]:
                    ev["boards"][board] = {"score": r["score"], "pinned_score": ref, "delta": r["score"] - ref,
                                           "unit": r["score_unit"], "rank": podium.index(r["model_id"]) + 1,
                                           "variant": r["variant"]}
        if not measured:   # recorded for the dossier / review, never a message (it names no model to adopt)
            record(conn, "challenger", p["task"], f'{p["pinned_model_id"]}:unmeasured',
                    {"pinned": p["pinned_model_id"], "note": "favourite absent from every leaderboard of this task"},
                    "baseline", p["role"])
            continue
        # 2026-10-14: one board is not enough (Grok Imagine 1.5 'agent' led Arena t2v while MiniMax H3
        # stays far ahead overall). A challenger must beat the favourite on the task's weighted composite of all
        # boards; the evidence keeps every board, lost ones included.
        from walter_router.analysis.scoring import composite   # late import (scoring -> select)
        comp = {c["model_id"]: c for c in composite(conn, p["task"], snaps)}
        mine_c = comp.get(p["pinned_model_id"])
        for model_id in list(found):
            theirs = comp.get(model_id)
            if mine_c and (not theirs or theirs["composite"] <= mine_c["composite"]):
                del found[model_id]
                continue
            found[model_id]["composite"] = {"challenger": theirs and theirs["composite"],
                                            "pinned": mine_c and mine_c["composite"],
                                            "rank": list(comp).index(model_id) + 1 if theirs else None,
                                            "pinned_rank": list(comp).index(p["pinned_model_id"]) + 1 if mine_c else None}
            found[model_id]["all_boards"] = {
                name: {"challenger": b.get("score"), "pinned": (mine_c["boards"].get(name) or {}).get("score") if mine_c
                       else None, "variant": b.get("variant"), "unit": b.get("unit"),
                       **_raw_measure(b, (mine_c["boards"].get(name) or {}) if mine_c else {})}
                for name, b in (theirs["boards"] if theirs else {}).items() if "score" in b}
        for model_id, ev in found.items():
            why = changes.changed(chg, model_id) + [f'{p["pinned_model_id"]} dégradé'
                                                     for _ in chg["nerf"].get(p["pinned_model_id"], [])[:1]]
            ev["why"] = why
            status = status_for_new if (why or status_for_new != "open") else "baseline"
            if record(conn, "challenger", p["task"], model_id, ev, status, p["role"]) and \
                    (status == "open" or status_for_new == "baseline"):
                created.append(f'{p["task"]}:{p["role"]}:{model_id}')
    return created


def unranked(conn) -> list[str]:
    """Models released recently on a provider with no measurement on any leaderboard yet (one alert per model)."""
    snaps = sel.latest_snapshots(conn)
    bench_ids = [snaps[k] for k in changes.BENCH_KINDS if k in snaps]
    created = []
    for o in conn.execute("""select o.model_id, o.interface, min(o.provider_created) as released
                             from models.offers o where o.snapshot_id = %s
                             and o.offer_key not like '%% | audio input'   -- a chat model that also hears: one release
                             and o.provider_created > now() - make_interval(days => %s)
                             and not exists (select 1 from models.benchmarks b where b.snapshot_id = any(%s)
                                             and b.model_id = o.model_id)
                             group by 1, 2""",
                          (snaps.get("openrouter"), UNRANKED_DAYS, bench_ids)):
        c = catalog.card(conn, o["model_id"], o["interface"])
        ev = {"interface": o["interface"], "released": o["released"], "name": c["name"], "modes": c["modes"],
              "providers": c["providers"], "prices": c["prices"]}
        if record(conn, "unranked", o["interface"], o["model_id"], ev, "open"):
            created.append(o["model_id"])
    return created


def stale_sources(conn) -> list[str]:
    created = []
    for r in conn.execute("""select kind, max(fetched_at) as at, now() - max(fetched_at) as age
                             from models.snapshots group by kind"""):
        limit = STALE_HOURS.get(r["kind"], 48)
        if r["age"].total_seconds() > limit * 3600:
            if record(conn, "source_stale", "", r["kind"], {"last": r["at"], "limit_hours": limit}, "open"):
                created.append(r["kind"])
        else:
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: source fresh again'
                            where kind = 'source_stale' and subject = %s and status in ('open', 'notified')""", (r["kind"],))
    return created


def boards_down(conn) -> list[str]:
    """2026-10-14: tell them when a leaderboard used by a task can no longer be read — the whole source
    stale for more than its limit, or one board empty in the latest snapshot while an earlier snapshot had rows
    (Arena image-edit, 2026-10-10: the task silently lost its model). One alert per outage; closed on recovery."""
    created = []
    age = {r["kind"]: r for r in conn.execute("""select kind, max(fetched_at) as at, now() - max(fetched_at) as age
                                                 from models.snapshots group by kind""")}
    for b in conn.execute("""select benchmark, bench_task, array_agg(task order by task) as tasks
                             from models.task_benchmarks where weight > 0 group by 1, 2""").fetchall():
        kind = sel.BENCH_KIND.get(b["benchmark"])
        if kind not in age:
            continue
        subject = f'{b["benchmark"]}:{b["bench_task"]}'
        stale = age[kind]["age"].total_seconds() > STALE_HOURS.get(kind, 60) * 3600
        last_ok = conn.execute("""select max(s.fetched_at) as at from models.snapshots s where s.kind = %s and exists
                                  (select 1 from models.benchmarks x where x.snapshot_id = s.snapshot_id
                                   and x.benchmark = %s and x.task = %s)""", (kind, b["benchmark"], b["bench_task"])).fetchone()["at"]
        empty_now = last_ok is not None and last_ok < age[kind]["at"]
        if stale or empty_now:
            ev = {"board": subject, "tasks": b["tasks"], "last_ok": last_ok, "source": kind,
                  "reason": "source inaccessible" if stale else "classement vide dans la dernière lecture"}
            if record(conn, "board_down", "", subject, ev, "open"):
                created.append(subject)
        else:
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: classement de nouveau lisible'
                            where kind = 'board_down' and subject = %s and status in ('open', 'notified')""", (subject,))
    return created


def tiers(conn, run_id: int | None = None, chg: dict | None = None) -> list[str]:
    """When the owner's method (nightly L1/L2/L3 in models.selection) designates another model x reasoning level than
    the declared tier, one alert per tier; they test and adopt or ignore (never switched automatically)."""
    run = {"run_id": run_id} if run_id else conn.execute("select run_id from models.latest_run").fetchone()
    if not run:
        return []
    created = []
    for r in conn.execute("""select s.level, s.model_id, s.variant, s.display_name, s.quality, s.real_cost,
                                    p.pinned_model_id, p.pinned_variant
                             from models.selection s join models.preferences p
                               on p.task = 'general' and p.role = s.level
                             where s.run_id = %s and s.task = 'general' and s.level in ('L1', 'L2', 'L3')""",
                          (run["run_id"],)):
        if (r["model_id"], r["variant"]) == (r["pinned_model_id"], r["pinned_variant"]):
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: méthode = niveau déclaré'
                            where kind = 'tier' and role = %s and status in ('open', 'notified')""", (r["level"],))
            continue
        pinned = conn.execute("""select score, cost from models.benchmarks b join models.latest_snapshots l using (snapshot_id)
                                 where b.benchmark = 'aa_intelligence' and b.model_id = %s and b.variant = %s limit 1""",
                              (r["pinned_model_id"], r["pinned_variant"])).fetchone()
        ev = {"level": r["level"], "proposed": f'{r["model_id"]}/{r["variant"]}', "name": r["display_name"],
              "score": r["quality"], "real_cost": r["real_cost"],
              "current": f'{r["pinned_model_id"]}/{r["pinned_variant"]}', "current_score": pinned and pinned["score"]}
        chg = chg or changes.events(conn)
        ev["why"] = changes.changed(chg, r["model_id"]) + [
            f'{r["pinned_model_id"]} dégradé' for _ in chg["nerf"].get(r["pinned_model_id"], [])[:1]] + \
            changes.rebased_intelligence(chg)
        if record(conn, "tier", "general", ev["proposed"], ev, "open" if ev["why"] else "baseline",
                   r["level"]) and ev["why"]:
            created.append(f'{r["level"]}:{ev["proposed"]}')
    return created


def adopt_orchestrator(conn, model_id: str) -> dict:
    """The owner adopted a new orchestrator: point Hermes model.default/provider at its first route (subscription
    first), config backed up, gateway restarted gracefully."""
    import shutil
    from datetime import datetime, timezone
    from walter_router.serve import execution
    if not instance.hermes_active():   # the engine's orchestrator is a Router poste: walter-llm follows the adoption
        return {"orchestrator": model_id, "applied": "walter-llm (Hermes retired)"}
    route = next((r for r in execution.routes(conn, model_id)
                  if r.get("probe_ok") is not False and r.get("hermes_provider")), None)
    if not route:
        raise RuntimeError(f"no usable route for {model_id}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(instance.hermes_home() / "config.yaml",
                 instance.hermes_home() / "backups" / "config" / f"config.yaml.{ts}.pre-orchestrator")
    for key, value in (("model.default", route["model"]), ("model.provider", route["hermes_provider"])):
        subprocess.run([str(HERMES), "config", "set", key, value], check=True, capture_output=True, timeout=60)
    subprocess.run([str(HERMES), "gateway", "restart"], capture_output=True, timeout=1900)
    return {"orchestrator": route["model"], "provider": route["hermes_provider"], "backup": ts}


def postes(conn) -> list[str]:
    """Orchestrator fiche de poste vs the model Hermes really runs: a clearly better one (>= margin) is proposed."""
    from walter_router.analysis import identity
    from walter_router.analysis import knowledge
    from walter_router.analysis import postes as postes_mod
    cfg = knowledge.load().get("postes", {}).get("orchestrator")
    if not cfg or not instance.hermes_active():   # the orchestrator poste = the model Hermes runs: none when retired
        return []
    ranking = postes_mod.rank(conn, "orchestrator", 20)
    cur = postes_mod.current_orchestrator()
    cur_id = identity.normalize("codex", cur["model"] or "")[0]
    current = next((r for r in ranking if r["model_id"] == cur_id), None)
    if not ranking or ranking[0]["model_id"] == cur_id:
        conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: orchestrateur déjà optimal'
                        where kind = 'tier' and role = 'orchestrator' and status in ('open', 'notified')""")
        return []
    top = ranking[0]
    if current and top["score"] - current["score"] < cfg.get("margin", 3.0):
        return []
    ev = {"level": "orchestrator", "poste": cfg["label"], "proposed": top["model_id"], "score": top["score"],
          "attributes": top["attributes"], "current": cur_id, "current_score": current and current["score"],
          "current_attributes": current and current["attributes"]}
    return [f'orchestrator:{top["model_id"]}'] if record(conn, "tier", "general", top["model_id"], ev, "open",
                                                            "orchestrator") else []


def nerfs(conn, run_id: int, chg: dict | None = None) -> list[str]:
    """An ACTIVE model (favourite, text tier, auto #1) lost score on a board of the task it is active for."""
    chg = chg or changes.events(conn)
    created = []
    active = [(r["task"], r["model_id"], r["why"]) for r in conn.execute(
        """select pinned_model_id as model_id, task, 'favori ' || role as why from models.preferences
           where pinned_model_id is not null
           union select model_id, task, 'n°1' from models.selection where run_id = %s and level = 'best' and rank = 1
             and task <> 'general'""", (run_id,))]
    for task, model_id, why in active:
        boards = {f'{b["benchmark"]}:{b["bench_task"]}' for b in conn.execute(
            "select benchmark, bench_task from models.task_benchmarks where task = %s", (task,))}
        hits = [n for n in chg["nerf"].get(model_id, []) if n["board"] in boards]
        if hits and record(conn, "nerf", task, model_id, {"active_as": why, "drops": hits}, "open"):
            created.append(f"{task}:{model_id}")
    return created


def pareto(conn, run_id: int, chg: dict | None = None) -> list[str]:
    """A price drop (or a release) that puts a model on the text Pareto frontier."""
    chg = chg or changes.events(conn)
    created = []
    for r in changes.frontier_entrants(conn, run_id):
        why = changes.changed(chg, r["model_id"])
        if not why:
            continue
        ev = {"name": r["display_name"], "variant": r["variant"], "score": r["quality"], "real_cost": r["real_cost"],
              "why": why}
        if record(conn, "pareto", "general", f'{r["model_id"]}/{r["variant"]}', ev, "open"):
            created.append(r["model_id"])
    return created


def billing(conn) -> list[str]:
    """Providers whose last probe found no credit left: one alert each, auto-cleared once topped up."""
    created = []
    for r in conn.execute("select provider, ok, detail from models.provider_status"):
        empty = not r["ok"] and (r["detail"] or "").startswith("crédit épuisé")
        if empty:
            if record(conn, "billing", "", r["provider"], {"detail": r["detail"]}, "open"):
                created.append(r["provider"])
        else:
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: crédit rechargé'
                            where kind = 'billing' and subject = %s and status in ('open', 'notified')""", (r["provider"],))
            conn.execute("delete from models.alerts where kind = 'billing' and subject = %s and status = 'dismissed'",
                         (r["provider"],))  # so a later outage alerts again
    return created


def _watched_interfaces(conn) -> set[str]:
    """Interfaces the owner has a declared preference on: new unranked releases there are worth a message."""
    # Text is governed by the tier method ('tier' alerts) and specialised tasks auto-pick their #1: no decision for
    # The owner there, so no podium messages for chat.
    return {r["interface"] for r in conn.execute(
        "select distinct t.interface from models.preferences p join models.tasks t using (task)")} - {"chat"}


def pending(conn) -> list[dict]:
    """What goes to Telegram. Unranked releases are recorded but never sent (too many, unproven): a new model is
    reported only when it ranks above an active model."""
    # 2026-10-02: only « a new model ranks above one of our active models » — favourites ('challenger'),
    # text tiers ('tier'), auto-picked #1 of specialised tasks ('new_best'). No credit, staleness or podium news.
    return list(conn.execute("""select * from models.alerts where status = 'open'
                                and kind in ('challenger', 'tier', 'new_best', 'nerf', 'pareto', 'board_down', 'plan_change')
                                and not (kind = 'tier' and role = 'orchestrator')
                                order by kind, task, alert_id"""))




def verdict(conn, alert_id: int, decision: str, note: str | None = None, role: str | None = None,
            _resolved: bool = False) -> dict:
    """Record the owner's answer. 'adopted' on a challenger also pins the challenger as the new favourite."""
    if decision not in ("adopted", "dismissed"):
        raise ValueError("decision must be adopted or dismissed")
    group = [] if _resolved else conn.execute("""select alert_id, role from models.alerts where ref = %s
                            and status = 'notified' and notified_at > now() - interval '30 days'""",
                                              (alert_id,)).fetchall()
    if group:  # The owner answers with the short number of the message (one number = one model, maybe several roles)
        if role:
            group = [g for g in group if g["role"] == role] or group
        if len(group) > 1:
            return {"ref": alert_id, "results": [verdict(conn, g["alert_id"], decision, note, _resolved=True)
                                                 for g in group]}
        alert_id = group[0]["alert_id"]
    a = conn.execute("update models.alerts set status = %s, verdict_note = %s where alert_id = %s returning *",
                     (decision, note, alert_id)).fetchone()
    if not a:
        raise KeyError(alert_id)
    if a["kind"] == "plan_change" and decision == "adopted":
        from walter_router.plan import declared
        e = a["evidence"]
        why = f"mail {e.get('vendor')} du {e.get('mail_date')} (alerte {alert_id})"
        if e["action"] == "none":   # a notice (offer ending): nothing to apply
            return {"alert_id": alert_id, "status": decision}
        done = declared.retire(e["sub_id"], why, source="email") if e["action"] == "retire" else \
            declared.upsert(e["sub_id"], e.get("fields") or {}, why, source="email")
        return {"alert_id": alert_id, "status": decision, "plans": done}
    if a["kind"] == "new_best" and decision == "adopted":
        from walter_router.serve.choose import set_preference
        set_preference(conn, a["task"], pin=a["subject"], watch="quality",
                       note=f"Adopté par {instance.owner()} (alerte {alert_id}).")
        return {"alert_id": alert_id, "status": decision, "pinned": a["subject"]}
    if a["kind"] == "new_best" and decision == "dismissed":
        from walter_router.serve.choose import set_preference
        set_preference(conn, a["task"], pin=a["evidence"]["previous"], watch="quality",
                       note=f"{instance.owner()} garde {a['evidence']['previous']} (alerte {alert_id} ignorée).")
        return {"alert_id": alert_id, "status": decision, "pinned": a["evidence"]["previous"]}
    if decision == "adopted" and a["kind"] == "tier" and a["role"] == "orchestrator":
        return {"alert_id": alert_id, "status": decision, **adopt_orchestrator(conn, a["subject"])}
    if decision == "adopted" and a["kind"] == "tier":
        from walter_router.analysis import knowledge
        from walter_router.serve.choose import set_preference
        ev = a["evidence"] or {}
        note = f"Niveau {a['role']} adopté par {instance.owner()} (alerte {alert_id}), méthode des 3 niveaux."
        knowledge.set_level("general", a["role"], a["subject"], why=f"alerte {alert_id} adoptée",
                            description=f"{ev.get('name') or a['subject']} ({ev.get('score')} AA) — {note}")
        set_preference(conn, "general", pin=a["subject"], role=a["role"], watch="dominance", note=note)
        return {"alert_id": alert_id, "status": decision, "pinned": a["subject"]}
    if decision == "adopted" and a["kind"] == "challenger" and ("boards" in a["evidence"] or "challenger" in a["evidence"]):
        from walter_router.serve.choose import set_preference
        set_preference(conn, a["task"], pin=a["subject"], role=a["role"] or "default",
                       note=f"Adopté par {instance.owner()} (alerte {alert_id}). {note or ''}".strip())
    return {"alert_id": alert_id, "status": decision}
