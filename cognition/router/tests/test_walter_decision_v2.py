"""Walter Decision 2.0 (2026-11-17): signals composed per event, parts split across the chain, hedged samples,
explicit unavailability, images on OpenRouter, dates written in words — offline."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
import decision as wd  # noqa: E402
import structured  # noqa: E402
from test_gateway_structured import Client, Resp, key  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    structured._unavailable.clear()
    wd.MEMO.clear()
    wd._COMPOSED.clear()
    needs = tmp_path / "needs.json"
    needs.write_text(json.dumps({"needs": {"hedged": {"sampling": {"mode": "first", "k": 2}}}}))
    monkeypatch.setattr(wd, "NEEDS_FILE", needs)
    wd._needs.update({"mtime": None, "data": {}})
    yield


def run(coro):
    return asyncio.run(coro)


def sig(module, name, question, **kw):
    return {"id": f"{module}.{name}", "module": module, "name": name, "occasions": kw.pop("occasions", ["turn"]),
            "layer": kw.pop("layer", "inference"), "question": question, "use": "a consumer reads it", **kw}


ACT = {"type": "choice", "criteria": {"new": "opens a subject", "continue": "same subject"}}
WORK = {"type": "noul", "instructions": "Work to carry out?"}
DATES = {"type": "spans", "instructions": "Every date or day mentioned.", "max": 8, "resolve": "date"}
SIGNALS = [sig("context", "act", ACT, required=True),
           sig("context", "thread", {"type": "choice", "criteria": {"new": "none of these"}}, options_from="threads",
               when=["threads"]),
           sig("context", "dates", DATES, layer="observation", when=["cue.date"]),
           sig("memory", "work", WORK),
           sig("memory", "deadline", {"type": "date", "order": "dmy"}, occasions=["incoming"], layer="observation"),
           sig("router", "work", WORK)]          # declared twice, identically: asked once


# ── compose ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_compose_keeps_the_occasion_and_the_facts_and_names_what_it_left_out():
    c = wd.compose(SIGNALS, "turn", set())
    assert list(c["questions"]) == ["act", "memory.work"]
    assert c["ids"]["memory.work"] == c["ids"]["router.work"]           # one question, two consumers
    assert c["skipped"] == {"context.thread": "when: threads", "context.dates": "when: cue.date"}
    assert "memory.deadline" not in c["ids"] and c["required"] == ["context.act"]


def test_compose_fills_the_callers_options_and_opens_a_question_on_a_cue():
    c = wd.compose(SIGNALS, "turn", {"threads", "cue.date"}, {"threads": {"t1": "continues: Router cycle"}})
    assert c["questions"]["thread"]["criteria"] == {"t1": "continues: Router cycle", "new": "none of these"}
    assert c["questions"]["dates"]["resolve"] == "date" and c["skipped"] == {}


def test_options_from_without_options_is_skipped_not_asked_empty():
    c = wd.compose(SIGNALS, "turn", {"threads"})
    assert c["skipped"]["context.thread"] == "options_from: no threads" and "thread" not in c["questions"]


def test_a_signal_outside_the_language_is_named():
    with pytest.raises(wd.Invalid, match="signal mod.bad"):
        wd.compose([sig("mod", "bad", {"type": "vote"})], "turn", set())


def test_compose_is_cached_by_its_inputs():
    a = wd.compose(SIGNALS, "turn", {"cue.date"}, registry="r1")
    a["questions"].clear()
    assert wd.compose(SIGNALS, "turn", {"cue.date"}, registry="r1")["questions"]   # a copy, never the cache


def test_cues_open_questions_without_a_model():
    assert wd.cues("Rappelle Sophie jeudi à 14h, 120 € à régler") >= {"cue.date", "cue.amount", "cue.person"}
    assert wd.cues("ok vas-y") == set()
    assert wd.holds(["a|b", "!c"], {"b"}) and not wd.holds(["a|b", "!c"], {"b", "c"})


# ── dates written in words ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("words,expect", [            # today = Tuesday 17/11/2026
    ("jeudi", {"date": "2026-11-19", "past": "2026-11-12", "ambiguous": True}),
    ("lundi dernier", {"date": "2026-11-16"}),
    ("lundi 30", {"date": "2026-11-30"}),
    ("demain 14h", {"date": "2026-11-18", "time": "14:00"}),
    ("le 3 décembre", {"date": "2026-12-03"}),
    ("05/12/2026", {"date": "2026-12-05"}),
    ("dans 3 jours", {"date": "2026-11-20"}),
    ("il y a 2 semaines", {"date": "2026-11-03"}),
    ("il y a deux semaines", {"date": "2026-11-03"}),
    ("dans trois jours", {"date": "2026-11-20"}),
    ("in two weeks", {"date": "2026-12-01"}),
    ("dans 10 jours", {"date": "2026-11-27"}),
    ("après-demain", {"date": "2026-11-19"}),
    ("le 4", {"date": "2026-12-04"}),
    ("mardi 2 décembre", {"date": "2026-12-02", "ambiguous": True}),   # the 2nd is a Wednesday: said, not guessed
    ("mardi 25/11 à 14h", {"date": "2026-11-25", "time": "14:00", "ambiguous": True}),   # the date wins, mismatch said
    ("mercredi 25/11", {"date": "2026-11-25"}),
    ("le 30/11 vers 9h", {"date": "2026-11-30", "time": "09:00"}),
    ("bientôt", None),
])
def test_dates_in_words_are_read_against_the_callers_day(words, expect):
    assert wd.resolve_date(words, "2026-11-17") == expect


def test_resolve_reads_every_passage_and_keeps_it_as_written():
    q = {"dates": DATES}
    a = {"dates": {"type": "spans", "spans": [{"text": "jeudi", "span": [3, 8], "found": 0.9},
                                              {"text": "plus tard", "span": [9, 18], "found": 0.6}]}}
    got = wd.resolve(q, a, "2026-11-17")["dates"]["spans"]
    assert got[0]["date"] == "2026-11-19" and got[0]["read_by"] == "walter" and got[0]["text"] == "jeudi"
    assert "date" not in got[1]


# ── execution ───────────────────────────────────────────────────────────────────────────────────────────────────
STATE = {"new_message": "On voit ça jeudi avec Sophie ?"}
BASE = {"act": {"type": "choice", "choice": "new", "probabilities": {"new": 0.8, "continue": 0.2}, "confidence": 0.8},
        "context.work": {"type": "noul", "noul": 0.7}, "memory.work": {"type": "noul", "noul": 0.7}}


def ext_reply(body):
    i = body["state"].index("jeudi")
    return 200, {"answers": {"dates": {"type": "list", "value": ["jeudi"], "spans": [[i, i + 5]], "confidences": [0.97]}},
                 "usage": {"input_tokens": 80, "cost": 0.000003}}


def test_an_occasion_composes_the_questions_and_answers_by_signal():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}}),
                     "alpha/extractions": ext_reply})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn", "now": "2026-11-17"},
        chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key, client=client, log=lambda e: None,
        signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200, out
    sent = {c["url"].split("/")[2]: c["json"] for c in client.calls}
    assert set(sent["console.nace.ai"]["questions"]) == {"act", "memory.work"}     # « work » twice: asked once
    assert list(sent["openrouter.ai"]["fields"]) == ["dates"] and "resolve" not in json.dumps(sent["openrouter.ai"])
    s = out["signals"]
    assert s["context.act"]["choice"] == "new" and s["memory.work"] == s["router.work"]
    assert s["context.dates"]["spans"][0]["date"] == "2026-11-19"
    assert out["model"] == "nace/drex-max-v1.1" and len(out["parts"]) == 2
    assert out["trace"]["skipped"] == {"context.thread": "when: threads"} and out["trace"]["unavailable"] == {}


def test_an_optional_part_that_fails_is_said_unavailable_and_the_rest_stands():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}}),
                     "alpha/extractions": (500, {"error": {"code": "boom"}})})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn"}, chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key,
        client=client, log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and out["signals"]["context.act"]["choice"] == "new"
    assert out["signals"]["context.dates"] is None
    assert out["trace"]["unavailable"]["context.dates"].startswith("failed: HTTP 500")


def test_a_required_part_that_fails_fails_the_decision():
    client = Client({"console.nace.ai": (500, {}), "alpha/decisions": (500, {}), "alpha/extractions": ext_reply})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn"}, chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key,
        client=client, log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 502 and "act" in out["failed"]


def test_an_optional_kind_no_model_carries_is_unavailable_without_a_call():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}})})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn"}, chain=["nace/drex-max-v1.1"], key=key, client=client,
        log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and len(client.calls) == 1
    assert out["trace"]["unavailable"]["context.dates"].startswith("unsupported")


def test_a_question_set_without_an_occasion_behaves_as_before():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}})})
    code, out = run(structured.decisions({"state": STATE, "questions": {"act": ACT}}, chain=["nace/drex-max-v1.1"],
                                         key=key, client=client, log=lambda e: None))
    assert code == 200 and "signals" not in out and "parts" not in out


def test_an_event_no_signal_concerns_costs_no_call():
    client = Client({})
    code, out = run(structured.decisions({"state": STATE, "occasion": "document"}, chain=["nace/drex-max-v1.1"],
                                         key=key, client=client, log=lambda e: None,
                                         signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and out["signals"] == {} and client.calls == []


def test_hedged_samples_keep_the_first_answer_and_cancel_the_other():
    class Slow(Client):
        n = 0

        async def post(self, url, headers=None, json=None, timeout=None):
            Slow.n += 1
            if Slow.n == 1:
                await asyncio.sleep(5)
            self.calls.append({"url": url, "json": json})
            return Resp(200, {"answers": {"act": BASE["act"]}, "usage": {"cost": 0.000002}})
    logs = []
    import time
    t0 = time.perf_counter()
    code, out = run(structured.decisions({"state": STATE, "questions": {"act": ACT}, "need": "hedged"},
                                         chain=["liquid/d1.2-ultra"], key=key, client=Slow({}), log=logs.append))
    assert code == 200 and time.perf_counter() - t0 < 2
    assert out["samples"] == 1 and out["sampling"] == "first"
    assert [c.get("skipped") for c in out["calls"]].count("hedged") == 1


def test_images_go_beside_the_state_on_openrouter_for_the_d1_2_family_only():
    client = Client({"alpha/decisions": (200, {"answers": {"act": BASE["act"]}, "usage": {"cost": 0.00001}})})
    code, out = run(structured.decisions(
        {"state": STATE, "questions": {"act": ACT}, "media": [{"type": "image", "data": "iVBORw0K"}]},
        chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key, client=client, log=lambda e: None))
    sent = client.calls[0]["json"]
    assert code == 200 and out["model"] == "liquid/d1.2-ultra" and len(client.calls) == 1
    assert sent["state"][0] == STATE and sent["state"][1] == {"type": "image_url",
                                                             "image_url": {"url": "data:image/png;base64,iVBORw0K"}}
    assert out["attempts"][0]["reason"].startswith("unsupported")       # Drex: no image route, named
    assert wd.capabilities("openrouter", "liquid/d1-ultra")["media"] == frozenset()


def test_the_cues_read_the_focus_not_the_history_beside_it():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}})})
    state = {"new_message": "ok vas-y", "previous_exchange": {"message": "On voit ça jeudi ?"}}
    code, out = run(structured.decisions(
        {"state": state, "occasion": "turn", "focus": "new_message"}, chain=["nace/drex-max-v1.1"], key=key,
        client=client, log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and out["trace"]["skipped"]["context.dates"] == "when: cue.date"
    code, out = run(structured.decisions({"state": state, "occasion": "turn", "focus": "nope"},
                                         chain=["nace/drex-max-v1.1"], key=key, client=client, log=lambda e: None,
                                         signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 400


def test_a_part_of_passages_only_is_read_once_whatever_the_samples():
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}}),
                     "alpha/extractions": ext_reply})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn", "samples": 3}, chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"],
        key=key, client=client, log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    hosts = [c["url"].split("/")[2] for c in client.calls]
    assert code == 200 and hosts.count("console.nace.ai") == 3 and hosts.count("openrouter.ai") == 1
    assert out["samples"] == 3


def test_hedged_readings_take_the_first_of_two_calls():
    # 17/11: OpenRouter's Extractions route answered the same kind of message in 0.1 to 3.6 s; passages are never
    # averaged, but two identical calls hedged keep the first that comes back
    class Slow(Client):
        n = 0

        async def post(self, url, headers=None, json=None, timeout=None):
            Slow.n += 1
            if Slow.n == 1:
                await asyncio.sleep(5)
            self.calls.append({"url": url, "json": json})
            return Resp(*ext_reply(json))
    import time
    t0 = time.perf_counter()
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn", "layers": ["observation"], "samples": 2, "sampling": "first",
         "now": "2026-11-17"}, chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key, client=Slow({}),
        log=lambda e: None, signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and time.perf_counter() - t0 < 2
    assert out["signals"]["context.dates"]["spans"][0]["date"] == "2026-11-19"
    assert [c.get("skipped") for c in out["calls"]].count("hedged") == 1


@pytest.mark.parametrize("written,value", [("300 euros", 300), ("1 200 €", 1200), ("89,90 €", 89.9),
                                           ("1,200.50 $", 1200.5), ("2k€", 2000), ("12,5", 12.5), ("rien", None)])
def test_an_amount_found_without_its_value_is_read_from_the_passage(written, value):
    assert wd.parse_number(written) == value
    got = wd.from_extraction({"type": "number", "unit": "EUR"}, {"value": None, "span": [0, len(written)], "p_null": 0},
                             written)
    assert got["number"] == value and (value is None or got["read_by"] == "walter")


def test_a_complementary_decision_asks_only_its_signals():
    c = wd.compose(SIGNALS, "turn", {"threads", "cue.date"}, {"threads": {"t1": "Router"}}, only=["context.dates"])
    assert list(c["questions"]) == ["dates"] and c["asked"] == ["context.dates"] and c["required"] == []
    assert wd.compose(SIGNALS, "turn", set(), only=["context.dates"])["skipped"] == {"context.dates": "when: cue.date"}
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}})})
    code, out = run(structured.decisions({"state": STATE, "occasion": "turn", "ask": ["memory.work"]},
                                         chain=["nace/drex-max-v1.1"], key=key, client=client, log=lambda e: None,
                                         signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 200 and out["trace"]["asked"] == ["memory.work"] and list(out["signals"]) == ["memory.work"]
    assert set(client.calls[0]["json"]["questions"]) == {"memory.work"}      # « work » is two modules' name
    for bad in (["memory.deadline"], [], "memory.work"):            # incoming only / empty / not a list
        code, out = run(structured.decisions({"state": STATE, "occasion": "turn", "ask": bad},
                                             chain=["nace/drex-max-v1.1"], key=key, client=client, log=lambda e: None,
                                             signals={"hash": "h1", "signals": SIGNALS}))
        assert code == 400


def test_readings_and_judgements_can_be_asked_apart():
    facts = {"threads", "cue.date"}
    opts = {"threads": {"t1": "Router"}}
    obs = wd.compose(SIGNALS, "turn", facts, opts, layers=["observation"])
    inf = wd.compose(SIGNALS, "turn", facts, opts, layers=["inference"])
    assert obs["asked"] == ["context.dates"] and "context.dates" not in inf["asked"]
    assert set(obs["asked"]) | set(inf["asked"]) == set(wd.compose(SIGNALS, "turn", facts, opts)["asked"])
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}})})
    code, _ = run(structured.decisions({"state": STATE, "occasion": "turn", "layers": ["guess"]},
                                       chain=["nace/drex-max-v1.1"], key=key, client=client, log=lambda e: None,
                                       signals={"hash": "h1", "signals": SIGNALS}))
    assert code == 400



def test_a_month_written_in_full_opens_the_date_question():
    # 17/11 bench: « dû le 1er décembre » and « je réserve la salle pour le 5 décembre » never asked their day
    assert "cue.date" in wd.cues("Rappel : le loyer de 650 € est dû le 1er décembre.")
    assert "cue.date" in wd.cues("Je réserve la salle pour le 5 décembre")
    assert "cue.date" not in wd.cues("je décide de rester à la maison")
    assert "cue.date" in wd.cues("la réunion avec Antoine il y a deux semaines")
    assert "cue.date" in wd.cues("Le 15 janvier 2027 je pars au Japon")


def test_a_duration_read_without_its_preposition_takes_it_back_from_the_passage():
    txt = "Le dossier complet doit nous être transmis dans 10 jours au plus tard."
    i = txt.find("10 jours")
    q = {"type": "date", "resolve": "date"}
    a = wd.from_extraction(q, {"value": None, "span": [i, i + 8], "p_null": 0.03}, txt)
    assert a["text"] == "dans 10 jours" and a["span"] == [txt.find("dans"), i + 8]
    assert wd.resolve({"d": q}, {"d": a}, "2026-11-17")["d"]["date"] == "2026-11-27"
    plain = "Il a mis 10 jours à répondre"            # no preposition: a length of time, no day
    j = plain.find("10 jours")
    b = wd.from_extraction(q, {"value": None, "span": [j, j + 8], "p_null": 0.03}, plain)
    assert b["text"] == "10 jours" and wd.resolve({"d": q}, {"d": b}, "2026-11-17")["d"].get("date") is None
    assert wd.resolve_date("d'ici 10 jours", "2026-11-17")["date"] == "2026-11-27"


def test_declared_relations_come_back_resolved_beside_what_the_models_said():
    rel = [{"id": "memory.work_not_new", "module": "memory", "type": "excludes", "if": {"signal": "memory.work", "above": 0.5},
            "then": {"signal": "context.act", "is": "new"}, "prefer": "none", "use": "reported only, for the test"}]
    client = Client({"console.nace.ai": (200, {"answers": BASE, "usage": {"input_tokens": 90}}),
                     "alpha/extractions": ext_reply})
    code, out = run(structured.decisions(
        {"state": STATE, "occasion": "turn", "now": "2026-11-17"},
        chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key, client=client, log=lambda e: None,
        signals={"hash": "h1", "signals": SIGNALS, "relations": rel}))
    assert code == 200, out
    res = out["resolution"]
    assert res["signals"] == out["signals"] and not res["changed"]                 # report-only: nothing changed
    broken = res["conflicts"] + res["uncertain_relations"]
    assert (out["signals"]["memory.work"]["noul"] >= 0.5) == bool(broken)
    code, plain = run(structured.decisions(
        {"state": STATE, "occasion": "turn", "now": "2026-11-17"},
        chain=["nace/drex-max-v1.1", "liquid/d1.2-ultra"], key=key, client=client, log=lambda e: None,
        signals={"hash": "h2", "signals": SIGNALS}))
    assert "resolution" not in plain                                               # no relation declared: as before
