"""Alerts: a pinned favourite overtaken, unranked new releases, stale sources — and their Telegram notification."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import catalog
from . import select as sel

HERMES = Path(os.environ.get("HERMES_HOME", "/root/.hermes")) / "hermes-agent" / "venv" / "bin" / "hermes"
UNRANKED_DAYS = 30
STALE_HOURS = {"aa": 48, "mm": 48, "da": 48, "arena": 48, "openrouter": 48, "kie": 48, "codex": 72}


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
                only_role: str | None = None) -> list[str]:
    """Models that overtake one of Monsieur's pinned favourites on any leaderboard of that task
    (models.task_benchmarks: AA, Design Arena, Arena.ai). One alert per challenger model, listing every board.

    watch = quality   -> any model scoring higher;
    watch = dominance -> scoring higher AND no more expensive per unit (ratio / budget picks);
    watch = none      -> never.
    """
    snaps = sel.latest_snapshots(conn)
    offers = sel.load_offers(conn, snaps)
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
            if _upsert(conn, "challenger", p["task"], model_id, ev, status_for_new, p["role"]):
                created.append(f'{p["task"]}:{p["role"]}:{model_id}')
    return created


def unranked(conn) -> list[str]:
    """Models released recently on a provider with no measurement on any leaderboard yet (one alert per model)."""
    snaps = sel.latest_snapshots(conn)
    bench_ids = [snaps[k] for k in ("aa", "mm", "da", "arena") if k in snaps]
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


def _watched_interfaces(conn) -> set[str]:
    """Interfaces Monsieur has a declared preference on: new unranked releases there are worth a message."""
    return {r["interface"] for r in conn.execute(
        "select distinct t.interface from models.preferences p join models.tasks t using (task)")}


def pending(conn) -> list[dict]:
    """What goes to Telegram. Unranked releases are recorded but never sent (too many, unproven): a new model is
    reported once it reaches a top 3 (kind 'top3') or overtakes a favourite from a top-3 place."""
    return list(conn.execute("""select * from models.alerts where status = 'open' and kind <> 'unranked'
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


def render(alerts: list[dict], conn=None) -> str:
    """Short Telegram message: one line per model (emoji name — modes — price per resolution — providers)."""
    beaten = [a for a in alerts if a["kind"] == "challenger"]
    beaten_models = {a["subject"] for a in beaten}
    podium = [a for a in alerts if a["kind"] == "top3" and a["subject"] not in beaten_models]
    stale = [a for a in alerts if a["kind"] == "source_stale"]
    out = ["Walter Router"]
    if beaten:
        out.append("⚠️ Favori dépassé (à tester) :")
        out += [f"• {_challenger_line(conn, a)}" for a in beaten]
    if podium:
        out.append("🏆 Nouveau dans le top 3 :")
        for a in podium:
            c = catalog.card(conn, a["subject"], a["evidence"]["interface"])
            ranks = ", ".join(f'{_short_board(b)} #{v["rank"]}' for b, v in a["evidence"]["boards"].items())
            out.append(f'• [{a["alert_id"]}] {catalog.line(c)} — {ranks}')
    if stale:
        out.append("Sources en retard : " + ", ".join(f'{a["subject"]} ({str(a["evidence"]["last"])[:10]})' for a in stale))
    if beaten:
        out.append("Après test : « adopter N » ou « ignorer N ».")
    return "\n".join(out)


def notify(conn, dry_run: bool = False) -> dict:
    alerts = pending(conn)
    if not alerts:
        return {"sent": 0}
    text = render(alerts, conn)
    if dry_run:
        return {"sent": 0, "dry_run": text}
    out = subprocess.run([str(HERMES), "send", "-t", "telegram", text], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return {"sent": 0, "error": (out.stderr or out.stdout)[-300:]}
    ids = [a["alert_id"] for a in alerts]
    conn.execute("update models.alerts set status = 'notified', notified_at = now() where alert_id = any(%s)", (ids,))
    return {"sent": len(ids)}


def verdict(conn, alert_id: int, decision: str, note: str | None = None) -> dict:
    """Record Monsieur's answer. 'adopted' on a challenger also pins the challenger as the new favourite."""
    if decision not in ("adopted", "dismissed"):
        raise ValueError("decision must be adopted or dismissed")
    a = conn.execute("update models.alerts set status = %s, verdict_note = %s where alert_id = %s returning *",
                     (decision, note, alert_id)).fetchone()
    if not a:
        raise KeyError(alert_id)
    if decision == "adopted" and a["kind"] == "challenger" and ("boards" in a["evidence"] or "challenger" in a["evidence"]):
        from .choose import set_preference
        set_preference(conn, a["task"], pin=a["subject"], role=a["role"] or "default",
                       note=f"Adopté par Monsieur (alerte {alert_id}). {note or ''}".strip())
    return {"alert_id": alert_id, "status": decision}
