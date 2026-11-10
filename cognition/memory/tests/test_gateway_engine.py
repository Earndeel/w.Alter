"""Engine lot E2 (2026-11-10): the gateway routes the engine's native intake and events use. Same writes as the hook
(Run Plane, bus), over HTTP; observations never reach the production bus. Runs whose origin.runtime is
'pytest-engine' and their events are removed at the end."""
import uuid

import pytest
from fastapi.testclient import TestClient

from walter_memory import gateway
from walter_memory.db import connect

RUNTIME = "pytest-engine"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gateway, "TOKEN", "t-engine")
    monkeypatch.setenv("WALTER_EPISODES", "off")
    c = TestClient(gateway.app)
    c.headers["Authorization"] = "Bearer t-engine"
    yield c
    with connect() as conn:
        ids = [str(r["run_id"]) for r in conn.execute(
            "select run_id from runs.runs where origin->>'runtime' = %s", (RUNTIME,))]
        conn.execute("delete from bus.events where source = %s or (source = 'runs' and subject = any(%s))",
                     (RUNTIME, ids))
        conn.execute("delete from runs.links where run_id::text = any(%s)", (ids,))
        conn.execute("delete from runs.runs where run_id::text = any(%s)", (ids,))


def origin(sid):
    return {"channel": "owner", "runtime": RUNTIME, "session_id": sid}


def status(run_id):
    with connect() as conn:
        return conn.execute("select status from runs.runs where run_id = %s", (run_id,)).fetchone()["status"]


def test_routes_refuse_a_caller_without_the_token(client):
    r = client.post("/v1/runs/start", json={"origin": origin("x")}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_one_turn_opens_one_run_even_when_replayed(client):
    sid, key = f"{RUNTIME}/vm/{uuid.uuid4()}", f"turn-{uuid.uuid4()}"
    a = client.post("/v1/runs/start", json={"origin": origin(sid), "goal": "bonjour Walter", "dedupe_key": key}).json()
    b = client.post("/v1/runs/start", json={"origin": origin(sid), "goal": "bonjour Walter", "dedupe_key": key}).json()
    assert a["run_id"] == b["run_id"] and a["privacy_class"] == "cloud_allowed"
    with connect() as conn:
        n = conn.execute("select count(*) n from runs.runs where origin->>'session_id' = %s", (sid,)).fetchone()["n"]
    assert n == 1


def test_a_goal_that_holds_a_secret_makes_a_local_only_run(client):
    sid = f"{RUNTIME}/vm/{uuid.uuid4()}"
    r = client.post("/v1/runs/start", json={"origin": origin(sid),
                                            "goal": "voici la clé <secret:redacted>"}).json()
    assert r["privacy_class"] == "local_only"


def test_a_new_turn_cancels_only_its_own_sessions_unfinished_run(client):
    s1, s2 = f"{RUNTIME}/vm/{uuid.uuid4()}", f"{RUNTIME}/vm/{uuid.uuid4()}"
    r1 = client.post("/v1/runs/start", json={"origin": origin(s1), "goal": "un"}).json()["run_id"]
    other = client.post("/v1/runs/start", json={"origin": origin(s2), "goal": "deux"}).json()["run_id"]
    client.post("/v1/runs/start", json={"origin": origin(s2), "goal": "trois", "cancel_run_id": r1})
    assert status(r1) == "open"                       # another session's run is never interrupted
    client.post("/v1/runs/start", json={"origin": origin(s2), "goal": "quatre", "cancel_run_id": other})
    assert status(other) == "cancelled"


def test_end_by_run_or_by_session_and_never_another_sessions_run(client):
    s1, s2 = f"{RUNTIME}/vm/{uuid.uuid4()}", f"{RUNTIME}/vm/{uuid.uuid4()}"
    r1 = client.post("/v1/runs/start", json={"origin": origin(s1), "goal": "un"}).json()["run_id"]
    assert client.post("/v1/runs/end", json={"run_id": r1, "session_id": s2}).json()["run_id"] is None
    assert status(r1) == "open"
    assert client.post("/v1/runs/end", json={"session_id": s1}).json()["run_id"] == r1
    assert status(r1) == "ended"
    r2 = client.post("/v1/runs/start", json={"origin": origin(s1), "goal": "deux"}).json()["run_id"]
    assert client.post("/v1/runs/end", json={"run_id": r2, "status": "failed"}).json()["run_id"] == r2
    assert status(r2) == "failed"
    assert client.post("/v1/runs/end", json={"run_id": "not-a-uuid"}).json()["run_id"] is None


def test_bus_takes_lifecycle_events_once_and_refuses_observations_and_other_types(client):
    sid, key = f"{RUNTIME}/vm/{uuid.uuid4()}", f"turn.ended/{uuid.uuid4()}"
    body = {"type": "turn.ended", "source": RUNTIME, "subject": sid, "payload": {"run_id": None}, "dedupe_key": key}
    first, again = client.post("/v1/bus/emit", json=body).json(), client.post("/v1/bus/emit", json=body).json()
    assert first["id"] and not first["duplicate"] and again["duplicate"]
    shadow = {**body, "dedupe_key": None, "payload": {"observation": True}}
    refused = client.post("/v1/bus/emit", json=shadow)
    assert refused.status_code == 403 and refused.json()["detail"]["refused"] == "observation_not_on_production_bus"
    other = client.post("/v1/bus/emit", json={**body, "type": "memory.derived"})
    assert other.status_code == 403 and other.json()["detail"]["refused"] == "type_not_open"
    assert client.post("/v1/bus/emit", json={"source": "dsh"}).status_code == 422   # malformed ≠ refused
    with connect() as conn:
        n = conn.execute("select count(*) n from bus.events where source = %s and subject = %s",
                         (RUNTIME, sid)).fetchone()["n"]
    assert n == 1


def test_privacy_classify_names_categories_never_the_text(client):
    r = client.post("/v1/privacy/classify", json={"text": "token <secret:redacted>"}).json()
    assert r["privacy_class"] == "local_only" and "sk-proj" not in str(r)
    assert client.post("/v1/privacy/classify", json={"text": "quelle heure est-il ?"}).json()["privacy_class"] == "cloud_allowed"


def test_a_replayed_turn_never_cancels_the_run_it_gets_back(client):
    sid, key = f"{RUNTIME}/vm/{uuid.uuid4()}", f"turn-{uuid.uuid4()}"
    r = client.post("/v1/runs/start", json={"origin": origin(sid), "goal": "un", "dedupe_key": key}).json()["run_id"]
    again = client.post("/v1/runs/start", json={"origin": origin(sid), "goal": "un", "dedupe_key": key,
                                                "cancel_run_id": r}).json()["run_id"]
    assert again == r and status(r) == "open"


def test_disclosure_check_for_the_engine_blocks_a_secret_and_never_echoes_it(client):
    leak = client.post("/v1/disclosure/check", json={"tool": "mcp__beeper__send_message",
                                                      "args": {"to": "inconnu@example.com", "text": "voici la clé sk-ant-api03-" + "x" * 40}})
    assert leak.status_code == 200 and leak.json()["action"] == "block"
    assert "sk-ant" not in leak.text
    plain = client.post("/v1/disclosure/check", json={"tool": "mcp__beeper__send_message", "args": {"to": "x", "text": ""}})
    assert plain.json()["action"] == "allow"
    assert client.post("/v1/disclosure/check", json={"tool": "x", "args": {}}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_a_delegation_run_is_filed_under_its_parent_run_and_an_unknown_parent_is_ignored(client):
    """Lot E5: a sub-agent the engine runs for another run is that run's child in the Run Plane."""
    parent = client.post("/v1/runs/start", json={"origin": origin(f"{RUNTIME}/vm/{uuid.uuid4()}"), "goal": "parent"}).json()["run_id"]
    child = client.post("/v1/runs/start", json={"origin": {**origin(f"{RUNTIME}/vm/{uuid.uuid4()}"), "channel": "machine"},
                                                "goal": "sous-tâche", "parent_run_id": parent}).json()["run_id"]
    orphan = client.post("/v1/runs/start", json={"origin": origin(f"{RUNTIME}/vm/{uuid.uuid4()}"), "goal": "x",
                                                 "parent_run_id": str(uuid.uuid4())}).json()["run_id"]
    with connect() as conn:
        rows = {str(r["run_id"]): r for r in conn.execute(
            "select run_id, parent_run_id::text p, origin->>'channel' ch from runs.runs where run_id::text = any(%s)",
            ([child, orphan],))}
    assert rows[child]["p"] == parent and rows[child]["ch"] == "machine"
    assert rows[orphan]["p"] is None
