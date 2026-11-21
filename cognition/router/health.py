"""Health of the Walter Router module: last refresh, source ages, providers, subscriptions, dossiers (`walter-router\nhealth`, shown by walter-core `walter_health`); the systemd OnFailure message after two failed cycles in a row."""
from __future__ import annotations

import subprocess

from walter_router.analysis import alerts
from walter_router.store import db
from walter_router.research.sources import arena_coverage

RUN_MAX_AGE_H = 54  # the cycle runs every 48 h


def status() -> dict:
    with db.connect() as conn:
        snaps = list(conn.execute("""select distinct on (kind) kind, fetched_at, row_count from models.snapshots
                                     order by kind, fetched_at desc"""))
        run = conn.execute("select run_id, finished_at, status from models.runs order by run_id desc limit 1").fetchone()
        open_alerts = conn.execute("select kind, status, count(*) as n from models.alerts group by 1, 2 order by 1, 2").fetchall()
        prefs = list(conn.execute("""select task, role, objective, pinned_model_id, pinned_variant, pinned_provider, watch
                                     from models.preferences order by task, role"""))
    return {"last_run": run, "sources": snaps, "alerts": open_alerts, "preferences": prefs}

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
        arena = conn.execute("""select raw from models.snapshots where kind = 'arena'
                                order by fetched_at desc, snapshot_id desc limit 1""").fetchone()
        coverage = {"arena": arena_coverage(arena["raw"])} if arena else {}
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
    if coverage.get("arena") and not coverage["arena"]["complete"]:
        warnings.append("source arena : collecte incomplète, anciens tableaux conservés lorsque disponibles")
    return {"ok": not issues, "issues": issues, "warnings": warnings, "providers": providers,
            "source_coverage": coverage,
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
    out = subprocess.run(["walter-telegram", "send", "--plain", "-"], input=text, capture_output=True, text=True,
                         timeout=120)                      # Walter's own Telegram door (2026-11-10)
    return {"sent": out.returncode == 0, "text": text}
