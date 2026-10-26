"""Memory Views v0: attachment (rule, decision, new), the subject card at two depths, reading by the MemoryViewQuery
contract. Real Postgres, fake models; sessions 'pytest-views-*' and the views they create are removed at the end."""
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
        self.cards = 0

    def decide(self, state, q, **kw):
        assert kw["privacy_class"] == "cloud_allowed"
        return {"answers": {"subject": {"choice": self.choice, "confidence": 0.9}}}

    def chat(self, messages, **kw):
        assert kw["poste"] == "memory_extraction"
        self.cards += 1
        return {"content": '{"title": "Banc des fils", "objective": "mesurer le rattachement", "state": "en_cours", '
                           f'"last": "étape {self.cards}"}}', "model": "fake/card"}


def embed(texts):
    rng = np.random.default_rng(abs(hash(texts[0][:20])) % 2**32)
    v = rng.normal(size=(len(texts), 256)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    with connection() as c:      # only subjects made of test exchanges alone are removed
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
    assert b == {"view_key": a["view_key"], "by": "rule", "confidence": None}
    llm.choice = "s0"
    with connection() as c:                      # the decision model picks the only candidate
        d = views.attach(c, ex(3, 30, "Et pour les nouveaux sujets, combien on en détecte maintenant ?"), embed=embed, llm=llm)
    assert d["view_key"] == a["view_key"] and d["by"] == "decision"
    llm.choice = "new"
    with connection() as c:
        e = views.attach(c, ex(4, 40, "Autre chose : configure la sortie WireGuard du Mac pour le navigateur"), embed=embed, llm=llm)
    assert e["by"] == "new" and e["view_key"] != a["view_key"]

    r = views.read({"depth": "overview", "key": a["view_key"]})
    assert r["version"] == 3 and "Titre : Banc des fils" in r["content"] and r["deeper"][0] == "synthesis"
    assert not r["stale"] and r["sources"] == [{"kind": "log", "session": SID, "seq": 3}]
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
