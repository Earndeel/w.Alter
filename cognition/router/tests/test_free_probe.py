"""2026-11-21 (owner): « la vérification du modèle et du provider doit être sans dépense » — provider checks never run
a model (no generation, no billed token); real traffic tells what a free check cannot see."""
import io
import json
from urllib.error import HTTPError

from walter_router.serve import execution


def _http_error(code, body=b"{}"):
    return HTTPError("https://x", code, "x", {}, io.BytesIO(body))


def test_a_refused_empty_request_means_endpoint_and_key_are_fine(monkeypatch):
    def fake(req, timeout=None):
        body = json.loads(req.data)
        assert not body.get("messages") and "input" not in body      # nothing a model could run on
        raise _http_error(400, b'{"error": "messages: at least one message is required"}')
    monkeypatch.setattr(execution, "urlopen", fake)
    ok, detail = execution._refused("https://api.kie.ai/claude/v1/messages", {"model": "m", "messages": []}, {})
    assert ok and "rien facturé" in detail


def test_a_bad_key_or_a_down_provider_is_not_ok(monkeypatch):
    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=None):
            return b'{"code": 401, "msg": "Unauthorized"}'
    monkeypatch.setattr(execution, "urlopen", lambda req, timeout=None: R())
    assert execution._refused("https://x", {}, {})[0] is False
    monkeypatch.setattr(execution, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(_http_error(503)))
    assert execution._refused("https://x", {}, {})[0] is False


def test_no_probe_sends_a_message_or_an_input(monkeypatch):
    sent = []

    def fake(req, timeout=None):
        if req.data:
            body = json.loads(req.data)
            sent.append(body)
            assert not body.get("messages") and not body.get("input") and not body.get("prompt")
            raise _http_error(400)
        raise _http_error(500)
    monkeypatch.setattr(execution, "urlopen", fake)
    monkeypatch.setattr(execution.instance, "secret_value", lambda name: "k")
    monkeypatch.setattr(execution, "recent_failures", lambda: {})

    class Conn:
        def execute(self, *a, **k):
            return self
    execution.probe(Conn())
    assert sent                       # the chat endpoints were checked, with requests no model can run


def test_three_failed_real_calls_in_a_row_flag_a_provider(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"at": now, "provider": "kie", "model": "gpt-6-1-sol", "ok": False}] * 3 + \
           [{"at": now, "provider": "kie", "model": "claude-opus-5-5", "ok": True},
            {"at": now, "provider": "openrouter", "model": "x", "ok": False},
            {"at": now, "provider": "openrouter", "model": "x", "ok": True},
            {"at": now, "provider": "venice", "model": "x", "ok": False, "skipped": "balance_below_floor"}] * 1
    log = tmp_path / "walter-llm.jsonl"
    log.write_text("first line is skipped\n" + "\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(execution.instance, "gateway_journal", lambda: log)
    assert execution.recent_failures() == {"kie-codex": 3}


def test_the_routable_kie_gpt_models_follow_kies_own_free_list(tmp_path, monkeypatch):
    state = tmp_path / "kie-codex-models.json"
    monkeypatch.setattr(execution.instance, "state_file", lambda name: state)
    offer = {"interface": "chat", "provider": "kie", "model_id": "gpt-7-sol", "offer_key": "gpt-7-sol", "pricing": {}}
    assert execution._runnable(offer) is None                    # not in the fallback list
    state.write_text(json.dumps({"models": ["gpt-7-sol"]}))
    assert execution._runnable(offer) == ("kie-codex", "gpt-7-sol", "kie-codex")
    assert execution._runnable({**offer, "model_id": "gpt-6-2-sol", "offer_key": "gpt-6-2-sol"}) is None


def test_the_agent_looks_only_at_the_top_of_the_basket():
    """Owner 2026-11-21: « que sur le haut du panier, y a des milliers de modèles obsolètes »."""
    from walter_router.research.agent import review
    from walter_router.store import db
    with db.connect() as conn:
        top = review.basket(conn)
        short = {r["model_id"] for r in conn.execute("select model_id from models.shortlist")}
        every = conn.execute("select count(distinct model_id) as n from models.catalog").fetchone()["n"]
        assert short <= set(top) and len(top) < every / 3
        assert all(u["closest_scored"] in top for u in review.unmatched(conn, 1000)
                   if "why" not in u)            # a name link only matters for a model the agent would look at
