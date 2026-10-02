"""Alerts: a pinned favourite overtaken, unranked new releases, stale sources — and their Telegram notification."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import select as sel

HERMES = Path(os.environ.get("HERMES_HOME", "/root/.hermes")) / "hermes-agent" / "venv" / "bin" / "hermes"
UNRANKED_DAYS = 30
STALE_HOURS = {"aa": 48, "mm": 48, "da": 48, "openrouter": 48, "kie": 48, "codex": 72}


def _upsert(conn, kind: str, task: str, subject: str, evidence: dict, status: str) -> bool:
    """Insert or refresh an alert; returns True when it is new. Verdicts and statuses are never overwritten."""
    row = conn.execute("""insert into models.alerts (kind, task, subject, evidence, status) values (%s, %s, %s, %s::jsonb, %s)
                          on conflict (kind, task, subject) do update set last_seen = now(), evidence = excluded.evidence
                          returning (xmax = 0) as inserted""",
                       (kind, task, subject, json.dumps(evidence, default=str), status)).fetchone()
    return bool(row["inserted"])


def challengers(conn, status_for_new: str = "open", only_task: str | None = None) -> list[str]:
    """Models measured strictly better than Monsieur's pinned favourite on that task's own leaderboard."""
    snaps = sel.latest_snapshots(conn)
    kinds = {"aa_intelligence": "aa", "aa_mm": "mm", "da_models": "da", "da_agents": "da"}
    created = []
    for p in conn.execute("""select p.*, t.quality_benchmark, t.quality_task, t.label from models.preferences p
                             join models.tasks t using (task) where p.pinned_model_id is not null
                             and t.quality_benchmark is not null and (%s::text is null or p.task = %s)""",
                          (only_task, only_task)).fetchall():
        sid = snaps.get(kinds[p["quality_benchmark"]])
        rows = list(conn.execute("""select model_id, variant, display_name, score, score_unit from models.benchmarks
                                   where snapshot_id = %s and benchmark = %s and task = %s""",
                                 (sid, p["quality_benchmark"], p["quality_task"])))
        mine = [r for r in rows if r["model_id"] == p["pinned_model_id"]
                and (not p["pinned_variant"] or r["variant"] == p["pinned_variant"])]
        if not mine:
            _upsert(conn, "challenger", p["task"], f'{p["pinned_model_id"]}:unmeasured',
                    {"pinned": p["pinned_model_id"], "note": "favourite absent from the leaderboard"}, status_for_new)
            continue
        ref = max(r["score"] for r in mine)
        offers = sel.load_offers(conn, snaps)
        for r in rows:
            if r["model_id"] == p["pinned_model_id"] or r["score"] <= ref:
                continue
            subject = f'{r["model_id"]}/{r["variant"]}' if r["variant"] else r["model_id"]
            callable_via = sorted({o["provider"] for o in offers.get(r["model_id"], [])})
            ev = {"task_label": p["label"], "pinned": p["pinned_model_id"], "pinned_score": ref,
                  "challenger": r["display_name"], "score": r["score"], "delta": r["score"] - ref,
                  "unit": r["score_unit"], "callable_via": callable_via}
            if _upsert(conn, "challenger", p["task"], subject, ev, status_for_new):
                created.append(subject)
    return created


def unranked(conn) -> list[str]:
    """Offers released recently on a provider whose model has no measurement on any leaderboard yet."""
    snaps = sel.latest_snapshots(conn)
    bench_ids = [snaps[k] for k in ("aa", "mm", "da") if k in snaps]
    created = []
    for o in conn.execute("""select o.* from models.offers o where o.snapshot_id = %s
                             and o.provider_created > now() - make_interval(days => %s)
                             and not exists (select 1 from models.benchmarks b where b.snapshot_id = any(%s)
                                             and b.model_id = o.model_id)""",
                          (snaps.get("openrouter"), UNRANKED_DAYS, bench_ids)):
        ev = {"provider": o["provider"], "offer_key": o["offer_key"], "interface": o["interface"],
              "released": o["provider_created"], "price_in_1m": o["price_in_1m"], "price_out_1m": o["price_out_1m"]}
        if _upsert(conn, "unranked", o["interface"], o["offer_key"], ev, "open"):
            created.append(o["offer_key"])
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


def render(alerts: list[dict]) -> str:
    lines = []
    for a in alerts:
        e = a["evidence"]
        if a["kind"] == "challenger" and "challenger" in e:
            via = ", ".join(e["callable_via"]) or "aucun provider autorisé pour l'instant"
            lines.append(f'• [{a["alert_id"]}] {e["task_label"]} : ton favori {e["pinned"]} ({e["pinned_score"]:.0f}) '
                         f'est dépassé par {e["challenger"]} ({e["score"]:.0f}, +{e["delta"]:.0f}). Dispo : {via}.')
        elif a["kind"] == "challenger":
            lines.append(f'• [{a["alert_id"]}] {a["task"]} : ton favori {e["pinned"]} n\'apparaît plus dans le classement.')
        elif a["kind"] == "unranked":
            lines.append(f'• [{a["alert_id"]}] Nouveau modèle {e["interface"]} pas encore classé : {e["offer_key"]} '
                         f'({e["provider"]}, sorti le {str(e["released"])[:10]}).')
        else:
            lines.append(f'• [{a["alert_id"]}] Source {a["subject"]} pas mise à jour depuis {str(e["last"])[:16]} UTC.')
    footer = []
    if any(a["kind"] == "challenger" for a in alerts):
        footer.append("Favori dépassé : teste le challenger, puis dis-moi « adopter N » ou « ignorer N ».")
    if any(a["kind"] == "unranked" for a in alerts):
        footer.append("Pas encore classé : à essayer si tu veux, je te redirai quand il aura un score mesuré.")
    return "Walter Router — à tester / à vérifier\n" + "\n".join(lines) + "\n\n" + "\n".join(footer)


def notify(conn, dry_run: bool = False) -> dict:
    alerts = pending(conn)
    if not alerts:
        return {"sent": 0}
    text = render(alerts)
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
    if decision == "adopted" and a["kind"] == "challenger" and "challenger" in a["evidence"]:
        from .choose import set_preference
        set_preference(conn, a["task"], pin=a["subject"], note=f"Adopté par Monsieur (alerte {alert_id}). {note or ''}".strip())
    return {"alert_id": alert_id, "status": decision}
