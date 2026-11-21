"""2026-11-21: an open padlock left medical on its #3 (stale proposal) and nothing noticed. The guardian now checks
the invariant on the ranking itself and puts the poste back on its #1 through the usual adoption path."""
import pytest


def test_an_open_padlock_off_its_first_is_detected_and_repaired(monkeypatch):
    from walter_router.analysis import telegram
    from walter_router.guardian import checks, run
    from walter_router.store import db
    sent = []
    monkeypatch.setattr(telegram, "notify_auto", lambda conn, changes, dry_run=False: sent.append(changes) or {})
    with db.connect() as conn:
        try:
            case = None
            for p in conn.execute("""select p.task, p.role, d.doc from models.preferences p
                                     join models.latest_dossiers d using (task)
                                     where not p.locked and p.pinned_model_id is not null and p.task <> 'general'"""):
                r = [x for x in (p["doc"].get("ranking") or []) if x.get("callable") and x.get("composite") is not None]
                if len(r) > 1 and r[0]["composite"] > r[1]["composite"] + checks.PADLOCK_MARGIN:
                    case = (p["task"], p["role"], r[0]["model_id"], r[1]["model_id"])
                    break
            if not case:
                pytest.skip("no open padlock with two callable ranked models")
            task, role, first, second = case
            conn.execute("update models.preferences set pinned_model_id = %s, pinned_variant = '' where task = %s and role = %s",
                         (second, task, role))
            # the morning's situation: the #1's own proposal closed by the Router (it used to block its return)
            conn.execute("""update models.alerts set status = 'dismissed', verdict_note = 'auto: x adopté (cadenas ouvert)'
                            where kind = 'challenger' and task = %s and subject = %s""", (task, first))
            drift = [x for x in checks.padlocks(conn) if x["subject"] == task]
            assert drift and drift[0]["detail"]["best"] == first and drift[0]["detail"]["in_use"] == second
            inc = {"incident_id": -1, "kind": "padlock_drift", "subject": task, "status": "open", "attempts": 0,
                   "detail": drift[0]["detail"]}
            run._padlock(conn, inc)
            now = conn.execute("select pinned_model_id from models.preferences where task = %s and role = %s",
                               (task, role)).fetchone()["pinned_model_id"]
            assert inc["status"] == "fixed" and now == first and sent and sent[0][0]["to"] == first
        finally:
            conn.rollback()
