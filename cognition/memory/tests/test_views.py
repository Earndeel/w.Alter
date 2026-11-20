"""Memory Views v0: attachment (rule, the preflight's thread, Walter Decision, new, not attached), the subject card at
two depths and its pace (A3), reading by the MemoryViewQuery contract. Test Postgres, fake models; sessions
'pytest-views-*', their runs and the views they create are removed at the end."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from walter_memory import views
from walter_memory.db import connection

RUN = uuid.uuid4().hex[:8]
SID = f"pytest-views-{RUN}"
# Far from any real exchange: candidates are subjects awake at the exchange time, so real ones never match.
T0 = datetime(2001, 1, 1, 10, 0, tzinfo=timezone.utc)


class FakeLLM:
    def __init__(self):
        self.choice = "new"
        self.confidence = 0.9
        self.work = 0.9
        self.cards = 0
        self.decisions = 0
        self.fail = False
        self.seen = []

    def decide(self, state, q, **kw):
        assert kw["privacy_class"] == "cloud_allowed" and q is None
        assert kw["occasion"] == "turn" and kw["ask"] == ["context.thread", "memory.work"]   # declared signals only
        self.decisions += 1
        if self.fail:
            raise TimeoutError("decision chain down")
        return {"signals": {"context.thread": {"choice": self.choice, "confidence": self.confidence},
                            "memory.work": {"noul": self.work}}}

    def chat(self, messages, **kw):
        assert kw["poste"] == "memory_extraction"
        self.cards += 1
        self.seen.append(json.loads(messages[1]["content"]))
        return {"content": '{"title": "Banc des fils", "objective": "mesurer le rattachement", "state": "en_cours", '
                           f'"last": "étape {self.cards}"}}', "model": "fake/card"}


def embed(texts):
    rng = np.random.default_rng(abs(hash(texts[0][:20])) % 2**32)
    v = rng.normal(size=(len(texts), 256)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture(autouse=True)
def quota_ok(monkeypatch):
    from walter_memory import quota
    monkeypatch.setattr(quota, "gate", lambda *a, **k: {"ok": True})


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    with connection() as c:      # only subjects made of test exchanges alone are removed
        c.execute("delete from runs.runs where origin->>'session_id' like %s", (f"pytest-views-{RUN}%",))
        c.execute("delete from walter_logs.events where session_id like %s", (f"pytest-views-{RUN}%",))
        c.execute("delete from walter_logs.sessions where session_id like %s", (f"pytest-views-{RUN}%",))
        c.execute("delete from views.member where session_id like %s and view_key is null", (f"pytest-views-{RUN}%",))
        keys = [r["view_key"] for r in c.execute(
            """select view_key from views.member group by view_key
               having bool_and(session_id like %s)""", (f"pytest-views-{RUN}%",)).fetchall()]
        c.execute("delete from views.ledger where view_key = any(%s)", (keys,))
        c.execute("delete from views.view where view_key = any(%s)", (keys,))


def ex(seq, minutes, message, answer="ok"):
    return {"session_id": SID, "seq": seq, "at": T0 + timedelta(minutes=minutes), "runtime": "claude_code",
            "message": message, "answer": answer}


def test_render_and_read_back_a_card():
    card = {"title": "Banc des fils", "objective": "mesurer", "state": "en_cours", "last": "fait"}
    index, overview = views._render(card)
    assert index == "Banc des fils — en_cours" and views._card_from(overview) == card


def test_attach_rule_decision_new_and_read_by_contract():
    llm = FakeLLM()
    with connection() as c:
        a = views.attach(c, ex(1, 0, "On lance le banc des fils sur les vrais messages de la semaine"), embed=embed, llm=llm)
    assert a["by"] == "new"
    with connection() as c:                      # a short reply minutes later: the rule, no decision call
        b = views.attach(c, ex(2, 5, "oui vas y"), embed=embed, llm=llm)
    assert b == {"view_key": a["view_key"], "by": "rule", "confidence": None, "card": "deferred"}   # A3
    llm.choice = "s0"
    with connection() as c:                      # the decision model picks the only candidate
        d = views.attach(c, ex(3, 30, "Et pour les nouveaux sujets, combien on en détecte maintenant ?"), embed=embed, llm=llm)
    assert d["view_key"] == a["view_key"] and d["by"] == "decision"
    llm.choice = "new"
    with connection() as c:
        e = views.attach(c, ex(4, 40, "Autre chose : configure la sortie WireGuard du Mac pour le navigateur"), embed=embed, llm=llm)
    assert e["by"] == "new" and e["view_key"] != a["view_key"]

    r = views.read({"depth": "overview", "key": a["view_key"]})
    # A3: the card of the creation only (the rule and the decision 5 and 30 min later are within the hour)
    assert r["version"] == 1 and "Titre : Banc des fils" in r["content"] and r["deeper"][0] == "synthesis"
    assert r["stale"] and r["sources"] == [{"kind": "log", "session": SID, "seq": 1, "why": "creation"}]   # said so
    s = views.read({"depth": "synthesis", "key": a["view_key"]})
    assert s["depth"] == "overview" and s["requested_depth"] == "synthesis"          # step E builds deeper depths
    src = views.read({"depth": "sources", "key": a["view_key"], "max_tokens": 200})
    assert [x["seq"] for x in src["sources"]] == [3, 2, 1]
    assert views.read({"depth": "index", "key": a["view_key"]})["content"] == "Banc des fils — en_cours"
    board = views.read({"depth": "index", "domain": "projects", "max_tokens": 4000})
    assert a["view_key"] in board["views"] and e["view_key"] in board["views"]
    assert "error" in views.read({"depth": "everything", "key": a["view_key"]})


def test_exchange_noise_filters():
    assert views.NOISE.match("<system-reminder> x") and views.NOISE.match("Base directory for this skill: /x")
    assert views._short("oui vas y")


def test_replies_versus_requests():
    for reply in ("oui", "Oui, lance le lot 0.", "oui met Lilou Martin", "vas y", "continue"):
        assert views._short(reply), reply
    for request in ("Ok Analyse completement l'etat de la VM et de walter",
                    "Est ce que l'architecture de walter peut etre considerer comme elegante ?"):
        assert not views._short(request), request


def test_a_transcript_ingested_twice_counts_once():
    class Conn:
        def execute(self, *a):
            return self

        def fetchall(self):
            base = dict(session_id="s", privacy_class="cloud_allowed", runtime="claude_code", platform="",
                        model="", session_privacy="cloud_allowed")
            return [{**base, "seq": 1, "type": "user/message", "occurred_at": T0, "text": "Première vraie demande sur le banc"},
                    {**base, "seq": 2, "type": "assistant/message", "occurred_at": T0, "text": "réponse 1"},
                    {**base, "seq": 3, "type": "user/message", "occurred_at": T0 + timedelta(minutes=9), "text": "Deuxième demande, plus récente"},
                    {**base, "seq": 4, "type": "assistant/message", "occurred_at": T0 + timedelta(minutes=9), "text": "réponse 2"},
                    {**base, "seq": 9, "type": "user/message", "occurred_at": T0, "text": "Première vraie demande sur le banc"},
                    {**base, "seq": 10, "type": "assistant/message", "occurred_at": T0, "text": "réponse 1"}]
    out = views.exchanges(Conn(), T0 - timedelta(days=1), T0 + timedelta(days=1))
    assert [(e["seq"], e["answer"]) for e in out] == [(1, "réponse 1"), (3, "réponse 2")]


def test_subject_candidates_for_a_new_message():
    llm = FakeLLM()
    sid = f"{SID}-cand"
    with connection() as c:
        a = views.attach(c, {**ex(10, 0, "Nouveau sujet de test pour les candidats"), "session_id": sid},
                         embed=embed, llm=llm)
    got = views.subject_candidates("Nouveau sujet de test pour les candidats", sid, at=T0 + timedelta(minutes=5),
                                   embed=embed)
    assert got["waiting"] == a["view_key"] and got["waiting_age_s"] == 300
    assert got["candidates"][0]["id"] == a["view_key"] and got["candidates"][0]["title"] == "Banc des fils"
    none = views.subject_candidates("", None, at=T0, embed=embed)
    assert none == {"candidates": [], "waiting": None, "waiting_age_s": None}


def _run(sid, minutes, thread, confidence, *, new=False, work=True, degraded=False):
    with connection() as c:
        c.execute("""insert into runs.runs (run_id, origin, started_at, thread_id, thread_choice, routing)
                     values (%s, %s, %s, %s, %s, %s)""",
                  (str(uuid.uuid4()), json.dumps({"session_id": sid, "runtime": "claude_code"}),
                   T0 + timedelta(minutes=minutes), thread,
                   json.dumps({"confidence": confidence, "new": new, "degraded": degraded}),
                   json.dumps({"requested": {"work": work}})))


def test_the_preflight_thread_is_reused_without_a_second_decision():
    """A1 (19/11): the turn's thread decision is on its run; Memory attaches from it and never asks again."""
    llm = FakeLLM()
    sid = f"{SID}-pf"
    _run(sid, 600, None, 0.9, new=True)                       # a sure « new » on a work turn opens a subject
    with connection() as c:
        a = views.attach(c, {**ex(20, 600, "Prépare le plan de migration du module de sauvegarde"), "session_id": sid},
                         embed=embed, llm=llm)
    assert a["by"] == "preflight_new" and a["view_key"] and llm.decisions == 0
    _run(sid, 640, a["view_key"], 0.8)                        # sure pick of that subject
    with connection() as c:
        b = views.attach(c, {**ex(22, 640, "Ajoute la vérification des sommes de contrôle à ce plan"), "session_id": sid},
                         embed=embed, llm=llm)
    assert (b["by"], b["view_key"]) == ("preflight", a["view_key"]) and llm.decisions == 0
    _run(sid, 650, "subject:doesnotexist", 0.3)               # unsure, another subject: not attached
    with connection() as c:
        u = views.attach(c, {**ex(24, 650, "Et la météo à Bangkok demain matin, il fera beau ?"), "session_id": sid},
                         embed=embed, llm=llm)
    assert u == {"view_key": None, "by": "unattached", "confidence": 0.3, "card": None} and llm.decisions == 0
    _run(sid, 660, a["view_key"], 0.35)                       # unsure, but where the session already is
    with connection() as c:
        s_ = views.attach(c, {**ex(26, 660, "Il faudra aussi documenter la restauration complète"), "session_id": sid},
                          embed=embed, llm=llm)
    assert (s_["by"], s_["view_key"]) == ("preflight_session", a["view_key"])
    _run(sid, 670, None, 0.95, new=True, work=False)          # a sure « new » that is no work: no subject
    with connection() as c:
        q = views.attach(c, {**ex(28, 670, "Quelle heure est-il à Paris en ce moment ?"), "session_id": sid},
                         embed=embed, llm=llm)
    assert q["by"] == "unattached" and llm.decisions == 0


def test_a_task_thread_joins_the_subject_its_first_exchange_opened():
    llm = FakeLLM()
    sid, task = f"{SID}-task", f"task:{uuid.uuid4()}"
    _run(sid, 900, task, 0.9, new=True)
    with connection() as c:
        a = views.attach(c, {**ex(30, 900, "Monte un banc de mesure des temps de réponse du routeur"), "session_id": sid},
                         embed=embed, llm=llm)
    assert a["by"] == "preflight_new"
    _run(f"{sid}-other", 960, task, 0.85)                    # the same objective resumed from another session
    with connection() as c:
        b = views.attach(c, {**ex(31, 960, "Reprends le banc du routeur, ajoute le p95 par fournisseur"),
                             "session_id": f"{sid}-other"}, embed=embed, llm=llm)
    assert (b["by"], b["view_key"]) == ("preflight", a["view_key"])


def test_without_a_preflight_decision_asks_once_and_a_failure_makes_no_subject():
    """Codex (no preflight) or a degraded preflight: Walter Decision with the declared signals; a failed or unsure
    call leaves the exchange not attached (13/11: 157 failed decisions had made 117 subjects)."""
    llm = FakeLLM()
    sid = f"{SID}-codex"
    _run(sid, 1200, None, 0.9, new=True, degraded=True)       # degraded: its thread is not reused
    with connection() as c:
        a = views.attach(c, {**ex(40, 1200, "Refactorise le parseur des journaux de Codex en deux fonctions"),
                             "session_id": sid}, embed=embed, llm=llm)
    assert a["by"] == "new" and llm.decisions == 1
    llm.fail = True
    with connection() as c:
        f = views.attach(c, {**ex(42, 1300, "Passe maintenant à l'index de recherche, il est trop lent"),
                             "session_id": sid}, embed=embed, llm=llm)
    assert f["by"] == "unattached" and f["view_key"] is None and llm.decisions == 2
    llm.fail, llm.choice, llm.confidence = False, "new", 0.4
    with connection() as c:
        g = views.attach(c, {**ex(44, 1400, "Une idée en passant sur l'ergonomie du portail"), "session_id": sid},
                         embed=embed, llm=llm)
    assert g["by"] == "unattached"
    with connection() as c:                                   # recorded: never retried, never a made-up subject
        n = c.execute("select count(*) n from views.member where session_id = %s and view_key is null", (sid,)).fetchone()
    assert n["n"] == 2


def test_the_card_is_rewritten_at_most_hourly_folding_the_messages_in_between():
    """A3 (19/11): creation, then once per hour of activity with the owner's messages since the card; sooner only when
    the owner says the subject ended or changes course; a quiet subject gets its last card from flush_cards."""
    llm = FakeLLM()
    sid = f"{SID}-card"
    with connection() as c:     # the logged messages the hourly card folds in
        c.execute("""insert into walter_logs.sessions (session_id, runtime, native_id) values (%s, 'claude_code', %s)""",
                  (sid, sid))
        for i, m in enumerate((10, 20, 30)):
            c.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, text, privacy_class, source_ref)
                         values (%s, %s, 'user/message', %s, %s, 'cloud_allowed', %s)""",
                      (sid, 51 + i, T0 + timedelta(minutes=2000 + m), f"Étape {i} de la rotation : liste les clés concernées",
                       f"test:{51 + i}"))
    _run(sid, 2000, None, 0.9, new=True)
    with connection() as c:
        a = views.attach(c, {**ex(50, 2000, "Ouvre un chantier sur la rotation des clés du coffre"), "session_id": sid},
                         embed=embed, llm=llm)
    key = a["view_key"]
    for i, m in enumerate((10, 20, 30)):
        _run(sid, 2000 + m, key, 0.9)
        with connection() as c:
            r = views.attach(c, {**ex(51 + i, 2000 + m, f"Étape {i} de la rotation : liste les clés concernées"),
                                 "session_id": sid}, embed=embed, llm=llm)
        assert r["card"] == "deferred"
    assert llm.cards == 1
    _run(sid, 2070, key, 0.9)
    with connection() as c:
        h = views.attach(c, {**ex(60, 2070, "On en est où de la rotation ?"), "session_id": sid}, embed=embed, llm=llm)
    assert h["card"] == "hourly" and llm.cards == 2
    assert len(llm.seen[-1]["earlier_owner_messages_since_the_card"]) == 3      # nothing said in between is lost
    _run(sid, 2080, key, 0.9)
    with connection() as c:
        d = views.attach(c, {**ex(62, 2080, "C'est fait, la rotation est terminée"), "session_id": sid},
                         embed=embed, llm=llm)
    assert d["card"] == "owner_changed_course" and llm.cards == 3
    _run(sid, 2090, key, 0.9)
    with connection() as c:
        views.attach(c, {**ex(64, 2090, "Note pour plus tard : prévoir la prochaine rotation dans six mois"),
                         "session_id": sid}, embed=embed, llm=llm)
        version = lambda: c.execute("""select max(version) v from views.version where view_key = %s
                                         and depth = 'overview'""", (key,)).fetchone()["v"]   # noqa: E731
        before = version()
        views.flush_cards(c, embed=embed, llm=llm, now=T0 + timedelta(minutes=2100))        # within the hour
        assert version() == before
        views.flush_cards(c, embed=embed, llm=llm, now=T0 + timedelta(minutes=2200))
        assert version() == before + 1


def test_the_quota_gate_defers_the_card_but_records_the_activity(monkeypatch):
    from walter_memory import quota
    llm = FakeLLM()
    sid = f"{SID}-quota"
    monkeypatch.setattr(quota, "gate", lambda *a, **k: {"ok": False, "reason": "limite réelle du fournisseur : HTTP 429 (71)"})
    _run(sid, 3000, None, 0.9, new=True)
    with connection() as c:
        a = views.attach(c, {**ex(70, 3000, "Lance l'audit des sauvegardes hors site de la semaine"), "session_id": sid},
                         embed=embed, llm=llm)
        row = c.execute("select last_at from views.view where view_key = %s", (a["view_key"],)).fetchone()
    assert llm.cards == 0 and row["last_at"] == T0 + timedelta(minutes=3000)
