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


def test_a_needs_owner_message_is_not_sent_again_on_the_next_passes(monkeypatch):
    """2026-11-21: Venice (no credit) was announced every other pass since 14/11."""
    from walter_router.guardian import run
    from walter_router.analysis import telegram
    sent = []
    monkeypatch.setattr(telegram, "send_with_buttons", lambda text, buttons: sent.append(text))

    class C:
        def __init__(self):
            self.verdict = None

        def execute(self, sql, args=None):
            if "set status" in sql and args[1] is not None:
                import json
                self.verdict = json.loads(args[1])
            if "set notified_at" in sql:
                import json
                self.verdict = json.loads(args[0])
            return self
    conn = C()
    inc = {"incident_id": 1, "kind": "credit_low", "subject": "openrouter", "status": "open", "attempts": 0,
           "detail": {"left_usd": 0.9, "step_usd": 1.0}, "verdict": None}
    for _ in range(4):                       # four guardian passes on the same incident
        inc = {**inc, "verdict": conn.verdict}
        inc["notified_status"] = (inc.get("verdict") or {}).get("notified_status")
        run.handle(conn, inc, [0])
        run.notify(conn, [inc])
    assert len(sent) == 1


def test_a_model_the_reference_has_not_measured_is_kept():
    """2026-11-21: svg left Fable 5.2 for GPT-6 Astra only because Design Arena had not measured Fable yet (Monsieur:
    « ils peuvent ne pas toujours être à jour avec les derniers modèles sortis »). Unmeasured ≠ worse."""
    from walter_router.guardian import checks
    from walter_router.store import db
    with db.connect() as conn:
        try:
            case = None
            for p in conn.execute("""select p.task, p.role, d.doc from models.preferences p
                                     join models.latest_dossiers d using (task)
                                     where not p.locked and p.pinned_model_id is not null and p.task <> 'general'"""):
                ranked = {x["model_id"] for x in (p["doc"].get("ranking") or []) if x.get("composite") is not None}
                if any(x.get("callable") and x.get("composite") is not None for x in p["doc"].get("ranking") or []):
                    case = (p["task"], p["role"], ranked)
                    break
            if not case:
                pytest.skip("no open padlock with a ranked callable model")
            task, role, ranked = case
            unmeasured = "test-unmeasured-model"
            assert unmeasured not in ranked
            conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (unmeasured,))
            conn.execute("update models.preferences set pinned_model_id = %s, pinned_variant = '' where task = %s and role = %s",
                         (unmeasured, task, role))
            assert not [x for x in checks.padlocks(conn) if x["subject"] == task]
        finally:
            conn.rollback()


def test_a_listed_model_its_provider_cannot_run_is_no_route():
    """2026-11-21: Kie lists Kimi K3.1 Pro, but its chat APIs only serve Claude and some GPT models."""
    from walter_router.analysis import alerts
    kimi = {"provider": "kie", "interface": "chat", "model_id": "kimi-k3-1-pro", "offer_key": "Kimi K3.1 Pro"}
    claude = {"provider": "kie", "interface": "chat", "model_id": "claude-opus-5-5", "offer_key": "claude-opus-5-5"}
    orr = {"provider": "openrouter", "interface": "chat", "model_id": "kimi-k3-1-pro", "offer_key": "moonshotai/kimi-k3.1-pro"}
    image = {"provider": "kie", "interface": "image", "model_id": "x-image", "offer_key": "x"}
    assert alerts._callable_via([kimi, orr]) == ["openrouter"]
    assert alerts._callable_via([claude]) == ["kie"]
    assert alerts._callable_via([image]) == ["kie"]
