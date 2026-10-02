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
        for b in boards:
            rows = _board_rows(conn, snaps, b["benchmark"], b["bench_task"])
            same = [r for r in rows if r["model_id"] == p["pinned_model_id"]]
            mine = [r for r in same if r["variant"] == p["pinned_variant"]] or same
            if not mine:
                continue
            measured = True
            ref = max(r["score"] for r in mine)
            board = f'{catalog.BOARDS.get(b["benchmark"], b["benchmark"])} {b["bench_task"]}'
            for r in rows:
                if r["model_id"] == p["pinned_model_id"] or r["score"] <= ref:
                    continue
                cost = _unit_cost(offers.get(r["model_id"], []), p["interface"], p["modes"])
                if p["watch"] == "dominance" and (cost is None or cost > ref_cost):
                    continue
                ev = found.setdefault(r["model_id"], {
                    "task_label": p["label"], "role": p["role"], "watch": p["watch"], "pinned": p["pinned_model_id"],
                    "pinned_unit_cost": ref_cost, "unit_cost": cost, "boards": {},
                    "callable_via": sorted({o["provider"] for o in offers.get(r["model_id"], [])})})
                prev = ev["boards"].get(board)
                if prev is None or r["score"] - ref > prev["delta"]:
                    ev["boards"][board] = {"score": r["score"], "pinned_score": ref, "delta": r["score"] - ref,
                                           "unit": r["score_unit"], "rank": (r["extra"] or {}).get("rank"),
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
    watched = _watched_interfaces(conn)
    rows = list(conn.execute("select * from models.alerts where status = 'open' order by kind, task, alert_id"))
    return [r for r in rows if r["kind"] != "unranked" or r["task"] in watched]


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
    gains = ", ".join(f'+{b["delta"]:.0f} {name.split()[0]}' + (f' #{b["rank"]}' if b.get("rank") else "")
                      for name, b in e["boards"].items())
    return (f'[{a["alert_id"]}] {e["task_label"]}{f" ({role})" if role else ""} : {c["name"]} dépasse {pinned} '
            f'({gains}) — {catalog.price_text(c)} — {", ".join(catalog.PROVIDERS.get(p, p) for p in c["providers"]) or "aucun provider"}')


def render(alerts: list[dict], conn=None) -> str:
    """Short Telegram message: one line per model (name — modes — price per resolution — providers)."""
    new = [a for a in alerts if a["kind"] == "unranked"]
    beaten = [a for a in alerts if a["kind"] == "challenger"]
    stale = [a for a in alerts if a["kind"] == "source_stale"]
    out = ["Walter Router"]
    if beaten:
        out.append("Favori dépassé (à tester) :")
        out += [f"• {_challenger_line(conn, a)}" for a in beaten]
    if new:
        out.append("Nouveaux, pas encore classés :")
        for a in new:
            c = catalog.card(conn, a["subject"], a["evidence"].get("interface") or a["task"]) if conn else None
            out.append(f'• [{a["alert_id"]}] {catalog.line(c) if c else a["subject"]}')
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
