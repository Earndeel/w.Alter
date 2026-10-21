"""The router's cycle as the analysis runs it: research collects (or the latest snapshots are re-derived), then the
data is understood and organised (owner knowledge, provider probes), the models are ranked and the active library
written (selection + dossiers), changes become alerts, and the owner is told on Telegram when needed."""
from __future__ import annotations

import json

from walter_router.analysis import alerts, changes, dossier, ingest, knowledge
from walter_router.analysis import select as sel
from walter_router.research import sources
from walter_router.serve import execution
from walter_router.store import db


def rederive(conn) -> dict:
    """Re-derive the latest snapshot of every source with the current identity rules (no network)."""
    out = {}
    for s in conn.execute("select kind, snapshot_id from models.latest_snapshots").fetchall():
        raw = conn.execute("select raw from models.snapshots where snapshot_id = %s", (s["snapshot_id"],)).fetchone()["raw"]
        with conn.transaction():
            out[s["kind"]] = {"snapshot_id": s["snapshot_id"], "rows": ingest._insert_rows(conn, s["snapshot_id"],
                                                                                            s["kind"], raw)}
    return out


def refresh(notify: bool = True, dry_run: bool = False, skip_collect: bool = False) -> dict:
    with db.connect() as conn:
        run_id = conn.execute("insert into models.runs default values returning run_id").fetchone()["run_id"]
        conn.commit()
        try:
            report = {"sources": rederive(conn) if skip_collect else sources.collect_all(conn, ingest.store)}
            with conn.transaction():
                report["knowledge"] = knowledge.declare(conn)  # config/knowledge.json is the source of truth
            if not skip_collect:
                with conn.transaction():
                    report["providers"] = execution.probe(conn)
            with conn.transaction():
                rows = sel.compute(conn)
                sel.save(conn, run_id, rows)
                report["selection_rows"] = len(rows)
                report["dossiers"] = dossier.build_all(conn, run_id)
                first = conn.execute("select count(*) as n from models.runs where status = 'ok'").fetchone()["n"] == 0
                chg = changes.events(conn)  # notifications are about what changed since the previous cycle
                report["changes"] = {k: sorted(v)[:30] for k, v in chg.items()}
                report["alerts"] = {"challengers": alerts.challengers(conn, "baseline" if first else "open", chg=chg),
                                    "new_best": alerts.new_best(conn, run_id, chg), "unranked": alerts.unranked(conn),
                                    "tiers": alerts.tiers(conn, run_id, chg),
                                    "nerfs": alerts.nerfs(conn, run_id, chg),
                                    "pareto": alerts.pareto(conn, run_id, chg),
                                    "stale": alerts.stale_sources(conn), "boards_down": alerts.boards_down(conn)}
                report["pruned_snapshots"] = sources.prune(conn)
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
