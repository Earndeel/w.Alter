"""Alerts: a pinned favourite overtaken, unranked new releases, stale sources — and their Telegram notification."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import os
import subprocess
from pathlib import Path

from . import catalog, changes, media
from . import select as sel

HERMES = Path(os.environ.get("HERMES_HOME", "/root/.hermes")) / "hermes-agent" / "venv" / "bin" / "hermes"
UNRANKED_DAYS = 30
STALE_HOURS = {"aa": 60, "mm": 60, "da": 60, "arena": 60, "bridgebench": 60, "openrouter": 60, "kie": 60,
               "codex": 60, "hermes_providers": 60, "declared": 24 * 365}  # 48 h cycle + 12 h margin


def _upsert(conn, kind: str, task: str, subject: str, evidence: dict, status: str, role: str = "") -> bool:
    """Insert or refresh an alert; returns True when it is new. Verdicts and statuses are never overwritten."""
    row = conn.execute("""insert into models.alerts (kind, task, role, subject, evidence, status)
                          values (%s, %s, %s, %s, %s::jsonb, %s)
                          on conflict (kind, task, role, subject) do update set last_seen = now(), evidence = excluded.evidence
                          returning (xmax = 0) as inserted""",
                       (kind, task, role, subject, json.dumps(evidence, default=str), status)).fetchone()
    return bool(row["inserted"])


def _unit_cost(offers: list[dict], interface: str, modes: list[str] | None = None) -> float | None:
    if interface == "chat":
        paid = sel.chat_route(offers, None)["paid"]
        return paid["blended_1m"] if paid else None
    paid = sel.media_route(offers, interface, modes)["paid"]
    return paid["cost"] if paid else None


def _board_rows(conn, snaps: dict, benchmark: str, bench_task: str) -> list[dict]:
    sid = snaps.get(sel.BENCH_KIND[benchmark])
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
    """Specialised tasks use their #1 automatically. When a run's #1 differs from the previous run's #1 and scores
    higher, Monsieur gets one line (the router already uses it; « ignorer N » keeps the previous one pinned)."""
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
        if old_q and old_q["quality"] >= r["quality"]:
            continue  # reshuffle by tie-break, not a better model
        chg = chg or changes.events(conn)
        why = changes.changed(chg, r["new_id"]) + [f'{r["old_id"]} dégradé' for _ in chg["nerf"].get(r["old_id"], [])[:1]]
        ev = {"task_label": r["label"], "interface": r["interface"], "name": r["display_name"], "score": r["quality"],
              "previous": r["old_id"], "previous_name": r["old_name"], "previous_score": old_q and old_q["quality"],
              "why": why}
        if _upsert(conn, "new_best", r["task"], r["new_id"], ev, "open" if why else "baseline") and why:
            created.append(f'{r["task"]}:{r["new_id"]}')
    return created


def top3(conn, status_for_new: str | None = None) -> list[str]:
    """A model entering the top 3 of a leaderboard in a domain Monsieur watches (interfaces he has preferences on).
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
        if _upsert(conn, "top3", interface, model_id, ev, status_for_new):
            created.append(f"{interface}:{model_id}")
    return created


def challengers(conn, status_for_new: str = "open", only_task: str | None = None,
                only_role: str | None = None, chg: dict | None = None) -> list[str]:
    """Models that overtake one of Monsieur's pinned favourites on any leaderboard of that task
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
            # Relevance (Monsieur, 2026-10-02): only a challenger in the board's top 3 is worth a message —
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
        if not measured:
            _upsert(conn, "challenger", p["task"], f'{p["pinned_model_id"]}:unmeasured',
                    {"pinned": p["pinned_model_id"], "note": "favourite absent from every leaderboard of this task"},
                    status_for_new, p["role"])
            continue
        for model_id, ev in found.items():
            why = changes.changed(chg, model_id) + [f'{p["pinned_model_id"]} dégradé'
                                                     for _ in chg["nerf"].get(p["pinned_model_id"], [])[:1]]
            ev["why"] = why
            status = status_for_new if (why or status_for_new != "open") else "baseline"
            if _upsert(conn, "challenger", p["task"], model_id, ev, status, p["role"]) and \
                    (status == "open" or status_for_new == "baseline"):
                created.append(f'{p["task"]}:{p["role"]}:{model_id}')
    return created


def unranked(conn) -> list[str]:
    """Models released recently on a provider with no measurement on any leaderboard yet (one alert per model)."""
    snaps = sel.latest_snapshots(conn)
    bench_ids = [snaps[k] for k in ("aa", "mm", "da", "arena", "bridgebench") if k in snaps]
    created = []
    for o in conn.execute("""select o.model_id, o.interface, min(o.provider_created) as released
                             from models.offers o where o.snapshot_id = %s
                             and o.provider_created > now() - make_interval(days => %s)
                             and not exists (select 1 from models.benchmarks b where b.snapshot_id = any(%s)
                                             and b.model_id = o.model_id)
                             group by 1, 2""",
                          (snaps.get("openrouter"), UNRANKED_DAYS, bench_ids)):
        c = catalog.card(conn, o["model_id"], o["interface"])
        ev = {"interface": o["interface"], "released": o["released"], "name": c["name"], "modes": c["modes"],
              "providers": c["providers"], "prices": c["prices"]}
        if _upsert(conn, "unranked", o["interface"], o["model_id"], ev, "open"):
            created.append(o["model_id"])
    return created


def stale_sources(conn) -> list[str]:
    created = []
    for r in conn.execute("""select kind, max(fetched_at) as at, now() - max(fetched_at) as age
                             from models.snapshots group by kind"""):
        limit = STALE_HOURS.get(r["kind"], 48)
        if r["age"].total_seconds() > limit * 3600:
            if _upsert(conn, "source_stale", "", r["kind"], {"last": r["at"], "limit_hours": limit}, "open"):
                created.append(r["kind"])
        else:
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: source fresh again'
                            where kind = 'source_stale' and subject = %s and status in ('open', 'notified')""", (r["kind"],))
    return created


def tiers(conn, run_id: int | None = None, chg: dict | None = None) -> list[str]:
    """When Monsieur's method (nightly L1/L2/L3 in models.selection) designates another model x reasoning level than
    the declared tier, one alert per tier; he tests and adopts or ignores (never switched automatically)."""
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
            f'{r["pinned_model_id"]} dégradé' for _ in chg["nerf"].get(r["pinned_model_id"], [])[:1]]
        if _upsert(conn, "tier", "general", ev["proposed"], ev, "open" if ev["why"] else "baseline",
                   r["level"]) and ev["why"]:
            created.append(f'{r["level"]}:{ev["proposed"]}')
    return created


def adopt_orchestrator(conn, model_id: str) -> dict:
    """Monsieur adopted a new orchestrator: point Hermes model.default/provider at its first route (subscription
    first), config backed up, gateway restarted gracefully."""
    import shutil
    from datetime import datetime, timezone
    from . import execution
    route = next((r for r in execution.routes(conn, model_id) if r.get("probe_ok") is not False), None)
    if not route:
        raise RuntimeError(f"no usable route for {model_id}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2("/root/.hermes/config.yaml", f"/root/.hermes/backups/config/config.yaml.{ts}.pre-orchestrator")
    for key, value in (("model.default", route["model"]), ("model.provider", route["hermes_provider"])):
        subprocess.run([str(HERMES), "config", "set", key, value], check=True, capture_output=True, timeout=60)
    subprocess.run([str(HERMES), "gateway", "restart"], capture_output=True, timeout=1900)
    return {"orchestrator": route["model"], "provider": route["hermes_provider"], "backup": ts}


def postes(conn) -> list[str]:
    """Orchestrator fiche de poste vs the model Hermes really runs: a clearly better one (>= margin) is proposed."""
    from . import identity, knowledge
    from . import postes as postes_mod
    cfg = knowledge.load().get("postes", {}).get("orchestrator")
    if not cfg:
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
    return [f'orchestrator:{top["model_id"]}'] if _upsert(conn, "tier", "general", top["model_id"], ev, "open",
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
        if hits and _upsert(conn, "nerf", task, model_id, {"active_as": why, "drops": hits}, "open"):
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
        if _upsert(conn, "pareto", "general", f'{r["model_id"]}/{r["variant"]}', ev, "open"):
            created.append(r["model_id"])
    return created


def billing(conn) -> list[str]:
    """Providers whose last probe found no credit left: one alert each, auto-cleared once topped up."""
    created = []
    for r in conn.execute("select provider, ok, detail from models.provider_status"):
        empty = not r["ok"] and (r["detail"] or "").startswith("crédit épuisé")
        if empty:
            if _upsert(conn, "billing", "", r["provider"], {"detail": r["detail"]}, "open"):
                created.append(r["provider"])
        else:
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: crédit rechargé'
                            where kind = 'billing' and subject = %s and status in ('open', 'notified')""", (r["provider"],))
            conn.execute("delete from models.alerts where kind = 'billing' and subject = %s and status = 'dismissed'",
                         (r["provider"],))  # so a later outage alerts again
    return created


def _watched_interfaces(conn) -> set[str]:
    """Interfaces Monsieur has a declared preference on: new unranked releases there are worth a message."""
    # Text is governed by the tier method ('tier' alerts) and specialised tasks auto-pick their #1: no decision for
    # Monsieur there, so no podium messages for chat.
    return {r["interface"] for r in conn.execute(
        "select distinct t.interface from models.preferences p join models.tasks t using (task)")} - {"chat"}


def pending(conn) -> list[dict]:
    """What goes to Telegram. Unranked releases are recorded but never sent (too many, unproven): a new model is
    reported only when it ranks above an active model."""
    # Monsieur 2026-10-02: only « a new model ranks above one of our active models » — favourites ('challenger'),
    # text tiers ('tier'), auto-picked #1 of specialised tasks ('new_best'). No credit, staleness or podium news.
    return list(conn.execute("""select * from models.alerts where status = 'open'
                                and kind in ('challenger', 'tier', 'new_best', 'nerf', 'pareto')
                                and not (kind = 'tier' and role = 'orchestrator')
                                order by kind, task, alert_id"""))


ROLE_LABELS = {"value": "ratio", "budget": "budget", "action": "action"}


def _challenger_line(conn, a: dict) -> str:
    e = a["evidence"]
    if "challenger" in e:  # alert recorded before 004 (single board)
        return f'[{a["alert_id"]}] {e["task_label"]} : {e["challenger"]} dépasse {e["pinned"]} (+{e["delta"]:.0f})'
    if "boards" not in e:
        return f'[{a["alert_id"]}] {a["task"]} : ton favori {e.get("pinned")} n\'apparaît dans aucun classement.'
    task = conn.execute("select interface, modes from models.tasks where task = %s", (a["task"],)).fetchone()
    c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
    pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])["name"]
    role = ROLE_LABELS.get(e.get("role"), "")
    gains = ", ".join(f'+{b["delta"]:.0f} {_short_board(name)} #{b["rank"]}' for name, b in e["boards"].items())
    return (f'[{a["alert_id"]}] {e["task_label"]}{f" ({role})" if role else ""} : {catalog.icon(c)} {c["name"]} dépasse {pinned} '
            f'({gains}) — {catalog.price_text(c)} — {", ".join(catalog.PROVIDERS.get(p, p) for p in c["providers"]) or "aucun provider"}')


def _short_board(name: str) -> str:
    return name.replace("text_to_", "t2").replace("image_to_", "i2").replace("_", " ")


def _fr(x, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",") if x is not None else "?"


def _head(c: dict) -> str:
    modes = f' · {media.short_modes(c["modes"])}' if c.get("modes") else ""
    return f'{catalog.icon(c)} {c["name"]}{modes}'


def _money_line(c: dict) -> str:
    prov = ", ".join(catalog.PROVIDERS.get(p, p) for p in c.get("providers") or [])
    return f'💰 {catalog.price_text(c)}' + (f' — {prov}' if prov else "")


def _why(e: dict) -> str | None:
    return ("🔎 " + " ; ".join(str(w) for w in e["why"][:3])) if e.get("why") else None


def _block(conn, a: dict) -> list[str]:
    e, n = a["evidence"], a.get("ref") or a["alert_id"]
    task = conn.execute("select label, interface, modes from models.tasks where task = %s", (a["task"],)).fetchone() \
        if a["task"] else None
    if a["kind"] == "challenger" and "boards" in e:
        c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
        pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])["name"]
        role = ROLE_LABELS.get(e.get("role"), "")
        gains = ", ".join(f'+{b["delta"]:.0f} {_short_board(k)} (#{b["rank"]})' for k, b in e["boards"].items())
        return [f'🆕 {n} · {task["label"]}{f" ({role})" if role else ""}', _head(c), _money_line(c),
                f'📈 dépasse {pinned} : {gains}', _why(e), f'→ « adopter {n} » ou « ignorer {n} »']
    if a["kind"] == "new_best":
        c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
        return [f'🆕 {n} · {task["label"]} — nouveau n°1, utilisé désormais', _head(c), _money_line(c),
                f'📈 dépasse {e["previous_name"]} : {e["score"]:.0f} vs {e["previous_score"] or 0:.0f}', _why(e),
                f'→ « ignorer {n} » pour garder {e["previous_name"]}']
    if a["kind"] == "tier":
        model_id, _, variant = a["subject"].partition("/")
        c = catalog.card(conn, model_id, "chat")
        cur = e.get("current", "")
        cur_id, _, cur_var = cur.partition("/")
        cur_name = catalog.card(conn, cur_id, "chat")["name"] + (f" ({cur_var})" if cur_var else "")
        return [f'📐 {n} · Niveau texte {e["level"]}', f'{_head(c)} ({variant})',
                f'📊 {_fr(e["score"], 1)} AA · {_fr(e["real_cost"], 3)} $/tâche',
                f'📈 remplacerait {cur_name}' + (f' ({_fr(e["current_score"], 1)} AA)' if e.get("current_score") else ""),
                _why(e), f'→ « adopter {n} » ou « ignorer {n} »']
    if a["kind"] == "nerf":
        c = catalog.card(conn, a["subject"], task["interface"] if task else "chat")
        drops = " ; ".join(f'{_short_board(d["board"].replace(":", " "))} {d["before"]:.0f} → {d["after"]:.0f}'
                           for d in e["drops"][:3])
        return [f'📉 {n} · Dégradation — {c["name"]} ({e["active_as"]}, {task["label"] if task else a["task"]})',
                f'   {drops}', f'→ le routeur réévalue au prochain cycle ; « ignorer {n} » pour masquer']
    if a["kind"] == "pareto":
        model_id, _, variant = a["subject"].partition("/")
        c = catalog.card(conn, model_id, "chat")
        return [f'💸 {n} · Entre dans la frontière de Pareto (texte)', f'{_head(c)} ({variant})',
                f'📊 {_fr(e["score"], 1)} AA · {_fr(e["real_cost"], 3)} $/tâche', _why(e)]
    return [f'• {n} · {a["kind"]} {a["subject"]}']


def _group_key(conn, a: dict) -> tuple:
    if a["kind"] != "challenger":
        return (a["alert_id"],)
    iface = conn.execute("select interface from models.tasks where task = %s", (a["task"],)).fetchone()
    return ("challenger", a["subject"], iface and iface["interface"])


def _challenger_group(conn, group: list[dict]) -> list[str]:
    """One block for one new model that beats several of Monsieur's choices (roles, t2v and i2v…)."""
    a0 = group[0]
    n = a0.get("ref") or a0["alert_id"]
    task = conn.execute("select interface, modes from models.tasks where task = %s", (a0["task"],)).fetchone()
    c = catalog.card(conn, a0["subject"], task["interface"], task["modes"])
    beats: dict[str, list[str]] = {}
    gains: dict[str, str] = {}
    for a in group:
        e = a["evidence"]
        pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])["name"]
        label = conn.execute("select label from models.tasks where task = %s", (a["task"],)).fetchone()["label"]
        role = {"default": "défaut"}.get(e.get("role"), ROLE_LABELS.get(e.get("role"), e.get("role")))
        beats.setdefault(pinned, []).append(f"{label.lower()}, {role}")
        best = max(e["boards"].items(), key=lambda kv: kv[1]["delta"])
        gains.setdefault(pinned, f'+{best[1]["delta"]:.0f} {_short_board(best[0])} (#{best[1]["rank"]})')
    lines = [f'🆕 {n} · {_head(c)}', _money_line(c), "📈 dépasse :"]
    lines += [f'   • {p} ({" ; ".join(sorted(set(r)))}) — {gains[p]}' for p, r in beats.items()]
    lines += [_why(a0["evidence"]), f'→ « adopter {n} » (ou « adopter {n} <rôle> ») · « ignorer {n} »']
    return lines


def render(alerts: list[dict], conn=None) -> str:
    """One airy block per piece of news (Monsieur, 2026-10-04): what it is, its price, what it beats, why now."""
    groups: dict[tuple, list[dict]] = {}
    for a in alerts:
        groups.setdefault(_group_key(conn, a), []).append(a)
    blocks = []
    for key, group in groups.items():
        lines = _challenger_group(conn, group) if key[0] == "challenger" else _block(conn, group[0])
        blocks.append("\n".join(x for x in lines if x))
    day = datetime.now(timezone.utc).strftime("%d/%m")
    return f"Walter Router — nouveautés du {day}\n\n" + "\n\n".join(blocks)


def _assign_refs(conn, alerts: list[dict]) -> list[dict]:
    """Short numbers Monsieur can answer with (1, 2, 3…), unique among alerts still awaiting his answer."""
    used = {r["ref"] for r in conn.execute("""select ref from models.alerts where ref is not null
                                              and status = 'notified' and notified_at > now() - interval '30 days'""")}
    out, n, by_group = [], 1, {}
    for a in alerts:
        key = _group_key(conn, a)
        if key not in by_group:
            while n in used:
                n += 1
            used.add(n)
            by_group[key] = n
        conn.execute("update models.alerts set ref = %s where alert_id = %s", (by_group[key], a["alert_id"]))
        out.append({**a, "ref": by_group[key]})
    return out


def notify(conn, dry_run: bool = False) -> dict:
    alerts = pending(conn)
    if not alerts:
        return {"sent": 0}
    alerts = _assign_refs(conn, alerts)
    text = render(alerts, conn)
    if dry_run:
        return {"sent": 0, "dry_run": text}
    out = subprocess.run([str(HERMES), "send", "-t", "telegram", text], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return {"sent": 0, "error": (out.stderr or out.stdout)[-300:]}
    ids = [a["alert_id"] for a in alerts]
    conn.execute("update models.alerts set status = 'notified', notified_at = now() where alert_id = any(%s)", (ids,))
    return {"sent": len(ids)}


def verdict(conn, alert_id: int, decision: str, note: str | None = None, role: str | None = None,
            _resolved: bool = False) -> dict:
    """Record Monsieur's answer. 'adopted' on a challenger also pins the challenger as the new favourite."""
    if decision not in ("adopted", "dismissed"):
        raise ValueError("decision must be adopted or dismissed")
    group = [] if _resolved else conn.execute("""select alert_id, role from models.alerts where ref = %s
                            and status = 'notified' and notified_at > now() - interval '30 days'""",
                                              (alert_id,)).fetchall()
    if group:  # Monsieur answers with the short number of the message (one number = one model, maybe several roles)
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
    if a["kind"] == "new_best" and decision == "dismissed":
        from .choose import set_preference
        set_preference(conn, a["task"], pin=a["evidence"]["previous"], watch="quality",
                       note=f"Monsieur garde {a['evidence']['previous']} (alerte {alert_id} ignorée).")
        return {"alert_id": alert_id, "status": decision, "pinned": a["evidence"]["previous"]}
    if decision == "adopted" and a["kind"] == "tier" and a["role"] == "orchestrator":
        return {"alert_id": alert_id, "status": decision, **adopt_orchestrator(conn, a["subject"])}
    if decision == "adopted" and a["kind"] == "tier":
        from .choose import set_preference
        set_preference(conn, "general", pin=a["subject"], role=a["role"], watch="dominance",
                       note=f"Niveau {a['role']} adopté par Monsieur (alerte {alert_id}), méthode des 3 niveaux.")
        return {"alert_id": alert_id, "status": decision, "pinned": a["subject"]}
    if decision == "adopted" and a["kind"] == "challenger" and ("boards" in a["evidence"] or "challenger" in a["evidence"]):
        from .choose import set_preference
        set_preference(conn, a["task"], pin=a["subject"], role=a["role"] or "default",
                       note=f"Adopté par Monsieur (alerte {alert_id}). {note or ''}".strip())
    return {"alert_id": alert_id, "status": decision}
