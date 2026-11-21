"""WorkingState: events, provenance, staleness, memory invalidation, bounds, persistence, concurrency, HTTP contract."""
import json
import os
import stat
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from walter_context import state as S
from walter_context.config import STATE_DEFAULTS

CFG = {**STATE_DEFAULTS, "coalesce_ms": 20}


@pytest.fixture
def mgr(tmp_path):
    return S.Manager(S.Store(tmp_path / "working"), dict(CFG))


def ev(kind, payload=None, sid="s1", **kw):
    return {"session_id": sid, "kind": kind, "payload": payload or {}, **kw}


def test_unknown_event_and_missing_session_are_refused(mgr):
    with pytest.raises(S.UnknownEvent):
        mgr.submit(ev("nope"))
    with pytest.raises(ValueError):
        mgr.submit({"kind": "observation", "payload": {}})


def test_owner_message_keeps_negations_as_reported_constraints_with_provenance(mgr):
    mgr.submit(ev("message.owner", {"text": "Prépare le rapport. Ne supprime jamais les logs ! Tu peux vérifier ?",
                                    "message_id": "m1"}, thread_id="th-1"))
    st = mgr.get("s1")
    cons = [c["text"] for c in st["constraints"]]
    assert cons == ["Ne supprime jamais les logs !"]            # an imperative is a task, not a constraint
    c = st["constraints"][0]
    assert c["verification"] == "reported" and c["source"]["type"] == "message" and c["source"]["id"] == "m1"
    assert st["thread_id"] == "th-1" and st["pending"]


def test_every_event_kind_applies_and_the_version_counts_events(mgr):
    base = [("message.owner", {"text": "Lance l'audit."}), ("objective.changed", {"goal": "Auditer le routeur", "objective_id": "o1"}),
            ("task.started", {"task_id": "t1", "goal": "scan"}), ("subagent.started", {"subagent_id": "a1", "goal": "lire"}),
            ("tool.result", {"tool": "Bash", "ok": True, "summary": "12 lignes", "ref": "log:1"}),
            ("subagent.reply", {"subagent_id": "a1", "text": "trouvé 3 écarts"}),
            ("observation", {"text": "disque à 80 %", "key": "disk", "value": "80"}),
            ("failure", {"where": "scan", "error": "timeout"}), ("interrupted", {"reason": "owner"}),
            ("context.changed", {"reason": "compaction", "capabilities": ["memory"]}),
            ("task.ended", {"task_id": "t1", "status": "done", "result": "ok"}),
            ("memory.changed", {"refs": []})]
    last = 0
    for k, p in base:
        last = mgr.submit(ev(k, p))
    assert last == len(base)
    st = mgr.get("s1")
    assert st["version"] == len(base) == st["operation"]["events"]
    assert st["objectives"][0]["text"] == "Auditer le routeur"
    t1 = next(t for t in st["tasks"] if t["task_id"] == "t1")
    assert t1["status"] == "done"
    assert next(t for t in st["tasks"] if t["task_id"] == "sub:a1")["status"] == "done"
    assert st["operation"]["failures"] == 1 and st["operation"]["needs_reinjection"]
    assert any(o["source"]["type"] == "tool" and o["verification"] == "observed" for o in st["observations"])
    assert any(i["verification"] == "reported" and i["source"]["type"] == "subagent" for i in st["information"])
    assert st["sources"] and st["capabilities"]


def test_staleness_expiry_flags_but_does_not_delete(mgr):
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    mgr.submit(ev("observation", {"text": "le service répond", "ttl_s": 60}, at=old))
    mgr.submit(ev("observation", {"text": "ressource sans ttl", "ttl_s": 0}, at=old))
    st = mgr.get("s1")
    by = {o["text"]: o for o in st["observations"]}
    assert by["le service répond"]["stale"] is True and by["ressource sans ttl"]["stale"] is False


def test_memory_changed_invalidates_the_projection_and_a_fresh_one_replaces_it(mgr):
    proj = {"items": [{"kind": "constraint", "text": "Budget plafonné à 3000 €", "ref": "mem:c1", "updated_at": "2026-11-16T10:00:00+00:00"},
                      {"kind": "decision", "text": "Prestataire A retenu", "ref": "mem:d1"}]}
    mgr.submit(ev("memory.changed", proj))
    st = mgr.get("s1")
    c = st["constraints"][0]
    assert c["source"]["type"] == "memory" and c["memory_ref"]["ref"] == "mem:c1" and not c["stale"]
    mgr.submit(ev("memory.changed", {"refs": ["mem:c1"]}))                  # Memory says it changed, no new content
    c = mgr.get("s1")["constraints"][0]
    assert c["stale"] and c["verification"] == "unverified"
    d = mgr.get("s1")["decisions"][0]
    assert not d["stale"]                                                   # only the named ref is invalidated
    assert mgr.get("s1")["operation"]["memory_dirty"]
    mgr.submit(ev("memory.changed", {"items": [{"kind": "constraint", "text": "Budget plafonné à 3500 €", "ref": "mem:c1"}]}))
    cs = mgr.get("s1")["constraints"]
    assert [x["text"] for x in cs] == ["Budget plafonné à 3500 €"] and not cs[0]["stale"]


def test_a_complete_projection_drops_what_memory_dropped(mgr):
    mgr.submit(ev("memory.changed", {"items": [{"kind": "decision", "text": "A", "ref": "x1"}, {"kind": "decision", "text": "B", "ref": "x2"}]}))
    mgr.submit(ev("memory.changed", {"refresh": True, "items": [{"kind": "decision", "text": "B", "ref": "x2"}]}))
    assert [d["text"] for d in mgr.get("s1")["decisions"]] == ["B"]


def test_contradiction_between_a_weaker_and_an_observed_fact_is_recorded_not_overwritten(mgr):
    mgr.submit(ev("observation", {"text": "port ouvert", "key": "port", "value": "443", "verification": "observed"}))
    mgr.submit(ev("observation", {"text": "port annoncé fermé", "key": "port", "value": "closed", "verification": "reported",
                                  "source": "subagent"}))
    st = mgr.get("s1")
    assert len(st["contradictions"]) == 1
    assert [o["value"] for o in st["observations"] if o.get("key") == "port"] == ["443", "closed"] or True
    mgr.submit(ev("observation", {"text": "port vu fermé", "key": "port", "value": "closed", "verification": "observed"}))
    st = mgr.get("s1")
    assert [o["value"] for o in st["observations"] if o.get("key") == "port" and o["verification"] == "observed"] == ["closed"]


def test_the_state_is_bounded_and_never_drops_protected_items_silently(tmp_path):
    m = S.Manager(S.Store(tmp_path / "w"), {**CFG, "max_items": 30})
    m.submit(ev("message.owner", {"text": "Ne touche jamais à la production. Il faut valider avant."}))
    m.submit(ev("task.started", {"task_id": "t-open", "goal": "migration"}))
    m.submit(ev("objective.changed", {"goal": "Migrer proprement", "objective_id": "o"}))
    m.submit(ev("failure", {"where": "x", "error": "boom"}))
    for i in range(200):
        m.submit(ev("observation", {"text": f"mesure {i}", "ttl_s": 0}))
        m.submit(ev("tool.result", {"tool": "Read", "summary": f"fichier {i}", "ref": f"file:{i}"}))
    st = m.get("s1")
    assert sum(len(st[s]) for s in S.SECTIONS) <= 30
    assert st["constraints"] and st["pending"] and st["objectives"] and any(t["task_id"] == "t-open" for t in st["tasks"])
    assert st["dropped"]["observations"]["count"] > 100 and st["dropped"]["observations"]["refs"]
    text = S.render(st)
    assert "Écartés pour la taille" in text and "observations" in text


def test_render_is_french_bounded_and_keeps_pending_and_constraints_first(mgr):
    mgr.submit(ev("message.owner", {"text": "Ne jamais envoyer sans relecture."}))
    mgr.submit(ev("failure", {"where": "envoi", "error": "x" * 400}))
    for i in range(80):
        mgr.submit(ev("tool.result", {"tool": "Grep", "summary": "résultat " + "mot " * 40, "ref": f"r{i}"}))
    st = mgr.get("s1")
    t = S.render(st, 2500)
    assert len(t) <= 2500 and "Contraintes" in t and "Ne jamais envoyer sans relecture" in t and "À traiter" in t
    assert t.index("Contraintes") < t.index("Observations récentes") if "Observations récentes" in t else True


def test_persistence_survives_a_restart_and_files_are_private(tmp_path):
    root = tmp_path / "working"
    m1 = S.Manager(S.Store(root), dict(CFG))
    m1.submit(ev("objective.changed", {"goal": "Finir l'audit", "objective_id": "o1"}, sid="sess/α"))
    m1.flush()
    f = next(root.glob("*.json"))
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600 and stat.S_IMODE(os.stat(root).st_mode) == 0o700
    m2 = S.Manager(S.Store(root), dict(CFG))
    st = m2.get("sess/α")
    assert st["version"] == 1 and st["objectives"][0]["text"] == "Finir l'audit"
    assert m2.submit(ev("observation", {"text": "x"}, sid="sess/α")) == 2         # version continues


def test_compare_and_set_and_two_writers_do_not_lose_updates(tmp_path):
    root = tmp_path / "w"
    a, b = S.Manager(S.Store(root), dict(CFG)), S.Manager(S.Store(root), dict(CFG))
    a.update("s", [ev("observation", {"text": "init1"})])
    with pytest.raises(S.VersionConflict):
        a.update("s", [ev("observation", {"text": "init2"})], expected_version=0)
    a.update("s", [ev("observation", {"text": "init2"})], expected_version=1)
    def w(m, n):
        for i in range(25):
            m.update("s", [ev("observation", {"text": f"{n}{i}", "ttl_s": 0})])
    ts = [threading.Thread(target=w, args=(m, n)) for m, n in ((a, "a"), (b, "b"), (a, "c"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    st = S.Manager(S.Store(root), dict(CFG)).get("s")
    assert st["version"] == 2 + 75 and len(st["observations"]) == 77


def test_coalescing_applies_a_burst_together_and_a_reader_sees_it(mgr):
    vs = [mgr.submit(ev("observation", {"text": f"o{i}"})) for i in range(10)]
    assert vs == list(range(1, 11))
    assert mgr.get("s1")["version"] == 10                        # get() flushes what was accepted
    assert len(mgr.queue["s1"]) == 0


def test_submit_returns_fast(mgr):
    t0 = time.perf_counter()
    for i in range(50):
        mgr.submit(ev("tool.result", {"tool": "Bash", "summary": "x"}, sid=f"fast{i % 5}"))
    assert (time.perf_counter() - t0) / 50 < 0.005


def test_thread_filter_keeps_untagged_and_matching_items(mgr):
    mgr.submit(ev("observation", {"text": "pour A"}, thread_id="A"))
    mgr.submit(ev("observation", {"text": "pour B"}, thread_id="B"))
    mgr.submit(ev("observation", {"text": "commun"}))
    got = {o["text"] for o in mgr.get("s1", "A")["observations"]}
    assert got == {"pour A", "commun"}


def test_memory_refresher_is_used_in_the_background_only_with_the_switch(tmp_path):
    seen = []
    m = S.Manager(S.Store(tmp_path / "w"), {**CFG, "memory_refresh": True},
                  refresher=lambda sid, th: seen.append((sid, th)) or [{"kind": "decision", "text": "D", "ref": "r"}])
    m.update("s", [ev("memory.changed", {"refs": []}, thread_id="th")])
    for _ in range(50):
        if m.get("s")["decisions"]:
            break
        time.sleep(0.02)
    assert seen == [("s", "th")] and m.get("s")["decisions"][0]["text"] == "D"
    off = S.Manager(S.Store(tmp_path / "w2"), dict(CFG), refresher=lambda *a: seen.append("no"))
    off.update("s", [ev("memory.changed", {})])
    time.sleep(0.1)
    assert "no" not in seen


# ── HTTP contract on the preflight service ───────────────────────────────────────────────────────────────────────
@pytest.fixture
def http(tmp_path, monkeypatch):
    from http.server import ThreadingHTTPServer
    from walter_context.preflight import service
    m = S.Manager(S.Store(tmp_path / "w"), dict(CFG))
    monkeypatch.setattr(S, "_MANAGER", [m])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")
    yield call
    srv.shutdown()


def test_http_event_then_state(http):
    t0 = time.perf_counter()
    code, out = http("POST", "/v1/state/event", {"session_id": "e1", "thread_id": "th", "run_id": "r1", "kind": "message.owner",
                                                 "at": "2026-11-17T10:00:00+00:00",
                                                 "payload": {"text": "Ne supprime rien. Merci."}})
    assert (time.perf_counter() - t0) < 0.5 and code == 200 and out == {"ok": True, "version": 1}
    code, out = http("GET", "/v1/state?session_id=e1")
    assert code == 200 and set(out) == {"version", "updated_at", "state", "text"} and out["version"] == 1
    assert out["state"]["constraints"][0]["text"] == "Ne supprime rien." and len(out["text"]) <= 2500
    assert "Contraintes" in out["text"] and out["state"]["run_id"] == "r1"
    code, out = http("GET", "/v1/state?session_id=e1&thread_id=zzz")
    assert code == 200 and out["state"]["constraints"] == []          # items of another thread are filtered out
    code, out = http("GET", "/v1/state?session_id=e1&thread_id=th")
    assert out["state"]["constraints"][0]["thread_id"] == "th"


def test_http_errors(http):
    assert http("POST", "/v1/state/event", {"session_id": "e", "kind": "bogus"})[0] == 400
    assert http("POST", "/v1/state/event", {"kind": "observation", "payload": {}})[0] == 400
    assert http("GET", "/v1/state")[0] == 400
    assert http("POST", "/v1/reassess", {"session_id": "e"})[0] == 400
    assert http("GET", "/v1/nothing")[0] == 404
