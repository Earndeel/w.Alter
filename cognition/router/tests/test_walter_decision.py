"""Walter Decision (2026-11-16): language check, needs registry, reuse, escalation, Liquid's own API — offline."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
import decision as wd  # noqa: E402
import structured  # noqa: E402
from test_gateway_structured import Client, key  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    structured._unavailable.clear()
    wd.MEMO.clear()
    needs = tmp_path / "needs.json"
    needs.write_text(json.dumps({"needs": {
        "fast": {"memo_ttl_s": 60, "escalate_below": 0.7},
        "never-reused": {"memo_ttl_s": 0},
        "capped": {"max_timeout_s": 2}}}))
    monkeypatch.setattr(wd, "NEEDS_FILE", needs)
    wd._needs.update({"mtime": None, "data": {}})
    yield
    wd.MEMO.clear()


def run(coro):
    return asyncio.run(coro)


Q = {"act": {"type": "choice", "criteria": {"new": "New subject", "continue": "Same subject"}},
     "extensive": {"type": "noul", "instructions": "Several sources?"}}


def answers(act=("new", 0.9), noul=0.95):
    return {"act": {"choice": act[0], "probabilities": {act[0]: act[1]}, "confidence": act[1]},
            "extensive": {"type": "noul", "noul": noul}, "note": {"text": "x"}}


# ── language ────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad,why", [
    ({}, "non-empty"),
    ({"a": {"type": "vote"}}, "type must be one of"),
    ({"a": {"type": "choice"}}, "needs criteria"),
    ({"a": {"type": "choice", "criteria": {"x": 3}}}, "descriptions"),
    ({"1a": {"type": "noul"}}, "question name"),
    ({"a": {"type": "noul", "instructions": "x" * 7000}}, "instructions"),
])
def test_a_malformed_decision_is_refused_before_any_provider_call(bad, why):
    with pytest.raises(wd.Invalid, match=why):
        wd.compile_questions(bad)
    client = Client({})
    code, out = run(structured.decisions({"state": {}, "questions": bad or {"a": {"type": "vote"}}}, chain=["m/x"],
                                         key=key, client=client, log=lambda e: None))
    assert code == 400 and client.calls == []


def test_the_schema_key_names_the_question_set_whatever_its_key_order():
    a = wd.compile_questions(Q)[1]
    b = wd.compile_questions(dict(reversed(list(Q.items()))))[1]
    c = wd.compile_questions({**Q, "extensive": {"type": "noul", "instructions": "other"}})[1]
    assert a == b and a != c


def test_confidence_reads_choice_noul_and_ignores_untyped_answers():
    got = wd.confidences(answers(("new", 0.55), 0.2))
    assert got == {"act": 0.55, "extensive": 0.8}


# ── reuse ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_same_decision_within_the_window_is_reused_without_a_call():
    logs = []
    client = Client({"alpha/decisions": (200, {"answers": answers(), "usage": {"cost": 0.00002, "prompt_tokens": 90}})})
    body = {"state": {"m": "salut"}, "questions": Q, "need": "fast"}
    c1, first = run(structured.decisions(dict(body), chain=["liquid/d1.1"], key=key, client=client, log=logs.append))
    c2, again = run(structured.decisions(dict(body), chain=["liquid/d1.1"], key=key, client=client, log=logs.append))
    assert c1 == c2 == 200 and len(client.calls) == 1
    assert again["reused"] is True and again["answers"] == first["answers"] and again["calls"] == []
    assert logs[0]["need"] == "fast" and logs[0]["schema"] == first["schema"] and logs[0]["confidence"]["act"] == 0.9
    assert logs[1]["reused"] is True and logs[1]["cost_usd"] == 0.0
    # another state, another chain, `reuse: false` or a need with no window: asked again
    run(structured.decisions({**body, "state": {"m": "autre"}}, chain=["liquid/d1.1"], key=key, client=client,
                             log=lambda e: None))
    run(structured.decisions({**body, "reuse": False}, chain=["liquid/d1.1"], key=key, client=client,
                             log=lambda e: None))
    run(structured.decisions({**body, "need": "never-reused"}, chain=["liquid/d1.1"], key=key, client=client,
                             log=lambda e: None))
    run(structured.decisions({**body, "need": "never-reused"}, chain=["liquid/d1.1"], key=key, client=client,
                             log=lambda e: None))
    assert len(client.calls) == 5


def test_an_undeclared_need_gets_the_default_policy():
    assert wd.policy("unknown") == wd.DEFAULT_POLICY and wd.policy(None) == wd.DEFAULT_POLICY
    assert wd.policy("fast")["escalate_below"] == 0.7 and wd.policy("fast")["declared"] is True


def test_a_need_caps_the_callers_timeout():
    seen = []

    class Slow(Client):
        async def post(self, url, headers=None, json=None, timeout=None):
            seen.append(timeout)
            return await super().post(url, headers=headers, json=json, timeout=timeout)
    client = Slow({"alpha/decisions": (200, {"answers": answers(), "usage": {}})})
    run(structured.decisions({"state": {}, "questions": Q, "need": "capped", "timeout": 30}, chain=["liquid/d1.1"],
                             key=key, client=client, log=lambda e: None))
    assert seen == [2.0]


# ── escalation ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_the_uncertain_questions_go_to_the_next_model_and_replace_their_answers():
    logs = []

    def reply(body):
        if body["model"] == "liquid/d1.1":
            return 200, {"answers": answers(("new", 0.52), 0.9), "usage": {"cost": 0.00001}}
        return 200, {"answers": {"act": {"choice": "continue", "probabilities": {"continue": 0.93},
                                         "confidence": 0.93}}, "usage": {"input_tokens": 400}}
    client = Client({"alpha/decisions": reply, "nace.ai": reply})
    code, out = run(structured.decisions({"state": {"m": "et l'autre ?"}, "questions": Q, "need": "fast"},
                                         chain=["liquid/d1.1", "nace/drex-max-v1.1"], key=key, client=client,
                                         log=logs.append))
    assert code == 200 and out["route"] == "openrouter/liquid/d1.1"
    assert out["escalated"] == {"model": "nace/drex-max-v1.1", "questions": ["act"]}
    assert out["answers"]["act"]["choice"] == "continue" and out["answers"]["extensive"]["noul"] == 0.9
    second = client.calls[1]
    assert "nace.ai" in second["url"] and list(second["json"]["questions"]) == ["act"]
    assert [c.get("escalation", False) for c in out["calls"]] == [False, True]
    assert logs[1]["escalation"] is True and logs[1]["need"] == "fast"


def test_no_escalation_without_a_threshold_or_a_next_model():
    client = Client({"alpha/decisions": (200, {"answers": answers(("new", 0.4), 0.5), "usage": {}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q}, chain=["liquid/d1.1", "cloudflare/clef"],
                                         key=key, client=client, log=lambda e: None))
    assert code == 200 and "escalated" not in out and len(client.calls) == 1
    code, out = run(structured.decisions({"state": {"x": 1}, "questions": Q, "need": "fast"}, chain=["liquid/d1.1"],
                                         key=key, client=client, log=lambda e: None))
    assert code == 200 and "escalated" not in out and len(client.calls) == 2


def test_a_failed_escalation_keeps_the_first_answers():
    def reply(body):
        return (200, {"answers": answers(("new", 0.5)), "usage": {}}) if body["model"] == "liquid/d1.1" else (503, {})
    client = Client({"alpha/decisions": reply, "nace.ai": (503, {})})
    code, out = run(structured.decisions({"state": {}, "questions": Q, "need": "fast"},
                                         chain=["liquid/d1.1", "nace/drex-max-v1.1"], key=key, client=client,
                                         log=lambda e: None))
    assert code == 200 and out["answers"]["act"]["choice"] == "new"
    assert out["escalated"] == {"model": "nace/drex-max-v1.1", "questions": ["act"], "error": "HTTP 503"}


# ── Liquid's own API ────────────────────────────────────────────────────────────────────────────────────────────
def test_liquid_d1_2_goes_to_liquids_own_api_with_its_own_key_and_price():
    logs = []
    client = Client({"api.liquid.ai": (200, {"answers": answers(), "usage": {"input_tokens": 1000}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q}, chain=["liquidai/d1.2-ultra"], key=key,
                                         client=client, log=logs.append))
    call = client.calls[0]
    assert code == 200 and out["route"] == "liquid/liquidai/d1.2-ultra" and out["provider"] == "liquid"
    assert call["url"] == structured.LIQUID_SYSTEMONE and call["json"]["model"] == "d1.2-ultra"
    assert call["headers"]["Authorization"] == "Bearer fixture-liquid_api_key"
    assert logs[0]["cost_usd"] == pytest.approx(1000 * 0.042 / 1e6) and logs[0]["cost_status"] == "estimated"
    assert structured.provider_of("liquid/d1-ultra") == "openrouter"          # OpenRouter's resale keeps its route


def test_liquid_without_its_grant_is_set_aside_and_the_chain_goes_on():
    def missing(name):
        if name == "LIQUID_API_KEY":
            raise structured.MissingGrant("missing_grant: LIQUID_API_KEY (grant liquid)")
        return key(name)
    client = Client({"nace.ai": (200, {"answers": answers(), "usage": {"input_tokens": 10}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q}, chain=["liquidai/d1.2", "nace/drex-max-v1.1"],
                                         key=missing, client=client, log=lambda e: None))
    assert code == 200 and out["model"] == "nace/drex-max-v1.1"
    assert out["attempts"][0]["model"] == "liquidai/d1.2" and "missing_grant" in out["attempts"][0]["reason"]
    assert "liquidai/d1.2" in structured._unavailable


# ── typed questions and routes (17/11/2026) ─────────────────────────────────────────────────────────────────────
MULTI = {"topics": {"type": "choice", "multiple": True, "instructions": "Which topics?",
                    "criteria": {"billing": "Charges", "delivery": "Shipping", "account": "Login"}}}
READ = {"amount": {"type": "number", "unit": "EUR", "instructions": "Amount of the bill?"},
        "due": {"type": "date", "instructions": "Pay by?"},
        "who": {"type": "text", "instructions": "Who must be told?"},
        "minutes": {"type": "number", "range": [0, 120], "step": 5, "instructions": "Minutes to handle it?"},
        "pii": {"type": "spans", "instructions": "Every piece of personal data."}}
STATE = {"message": "Payer EDF 84,30 € avant le 12/12/2026, prévenir Paul Martin."}


@pytest.mark.parametrize("bad,why", [
    ({"a": {"type": "choice", "multiple": "yes", "criteria": {"x": "X"}}}, "multiple is true or false"),
    ({"a": {"type": "number", "range": [5, 1]}}, "low < high"),
    ({"a": {"type": "number", "range": [0, 10], "step": 3}}, "divide"),
    ({"a": {"type": "number", "step": 1}}, "step goes with range"),
    ({"a": {"type": "spans", "max": 99}}, "max is an integer"),
])
def test_typed_questions_are_checked_before_any_call(bad, why):
    with pytest.raises(wd.Invalid, match=why):
        wd.compile_questions(bad)


def test_the_plan_says_what_each_route_carries():
    p = wd.plan("openrouter", "liquid/d1.2", {**Q, **MULTI, **READ})
    assert set(p["native"]) == {"act", "extensive", "topics.option0", "topics.option1", "topics.option2"}
    assert set(p["extract"]) == set(READ) and list(p["emulated"]) == ["topics"]
    with pytest.raises(wd.Unsupported, match=r"amount \(number\).*minutes \(estimate\)"):
        wd.plan("openrouter", "liquid/d1-ultra", READ)                  # no Extractions route for d1-ultra
    with pytest.raises(wd.Unsupported, match=r"who \(text\)"):
        wd.plan("nace", "nace/drex-max-v1.1", READ)
    with pytest.raises(wd.Unsupported, match="media audio"):
        wd.plan("openrouter", "liquid/d1.2", Q, [{"type": "audio", "data": "UklGRg=="}])
    native = wd.plan("liquid", "liquidai/d1.2", {**MULTI, **READ, "face": {"type": "box"}},
                     [{"type": "image", "data": "x"}, {"type": "audio", "data": "x"}])    # a box needs one image
    assert set(native["native"]) == {"topics", *READ, "face"} and not native["extract"] and not native["emulated"]


def test_several_options_are_asked_as_one_noul_each_never_as_multiple():
    """17/11: OpenRouter and Nace accept `multiple: true` and silently answer ONE option."""
    def reply(body):
        q = body["questions"]
        assert all(v["type"] == "noul" and "multiple" not in v for v in q.values())
        p = {"topics.option0": 0.97, "topics.option1": 0.91, "topics.option2": 0.02}
        return 200, {"answers": {k: {"type": "noul", "noul": p[k]} for k in q}, "usage": {"cost": 0.00001}}
    client = Client({"alpha/decisions": reply})
    code, out = run(structured.decisions({"state": STATE, "questions": MULTI}, chain=["nace-ai/drex-max"], key=key,
                                         client=client, log=lambda e: None))
    assert code == 200 and len(client.calls) == 1
    assert out["answers"]["topics"] == {"type": "choice", "choices": ["billing", "delivery"], "emulated": "noul",
                                        "probabilities": {"billing": 0.97, "delivery": 0.91, "account": 0.02}}
    assert wd.confidence(out["answers"]["topics"]) == pytest.approx(0.91)


def test_values_go_to_the_extractions_route_in_parallel_and_come_back_in_the_canonical_shape():
    text = wd.render_state(STATE)
    a, b = text.index("84,30 €"), text.index("12/12/2026")
    n = text.index("Paul Martin")

    def extract(body):
        assert body["state"] == text and body["model"] == "liquid/d1.2"
        f = body["fields"]
        assert f["minutes"] == {"type": "estimate", "min": 0, "max": 120, "step": 5, "instructions": "Minutes to handle it?"}
        assert f["pii"]["type"] == "list" and f["pii"]["items"] == "text" and f["amount"]["unit"] == "EUR"
        return 200, {"answers": {
            "amount": {"type": "number", "value": 84.3, "span": [a, a + 7], "p_null": 0},
            "due": {"type": "date", "value": "2026-12-12", "span": [b, b + 10], "p_null": 0.01},
            "who": {"type": "text", "value": "Paul Martin", "span": [n, n + 11], "p_null": 0.02},
            "minutes": {"type": "estimate", "value": 10, "median": 10, "p10": 0, "p90": 25},
            "pii": {"type": "list", "value": ["Paul Martin"], "spans": [[n, n + 11]], "confidences": [0.99]}},
            "usage": {"input_tokens": 300, "cost": 0.000006}}
    client = Client({"alpha/decisions": (200, {"answers": answers(), "usage": {"cost": 0.000004, "prompt_tokens": 90}}),
                     "alpha/extractions": extract})
    code, out = run(structured.decisions({"state": STATE, "questions": {**Q, **READ}}, chain=["liquid/d1.2"],
                                         key=key, client=client, log=lambda e: None))
    assert code == 200 and len(client.calls) == 2
    got = out["answers"]
    assert list(got) == ["act", "extensive", *READ]
    assert got["amount"] == {"type": "number", "number": 84.3, "unit": "EUR", "text": "84,30 €", "span": [a, a + 7],
                             "found": 1.0}
    assert got["due"]["date"] == "2026-12-12" and got["due"]["text"] == "12/12/2026" and got["due"]["found"] == 0.99
    assert got["who"] == {"type": "text", "text": "Paul Martin", "span": [n, n + 11], "found": 0.98}
    assert got["minutes"] == {"type": "number", "number": 10, "interval": [0, 25], "unit": None}
    assert got["pii"]["spans"] == [{"text": "Paul Martin", "span": [n, n + 11], "found": 0.99}]
    assert out["calls"][0]["cost_usd"] == pytest.approx(0.00001)


def test_a_question_no_model_of_the_chain_can_carry_is_refused_by_name_without_a_call():
    client = Client({})
    code, out = run(structured.decisions({"state": STATE, "questions": {"face": {"type": "box"}}},
                                         chain=["liquid/d1.2", "nace/drex-max-v1.1"], key=key, client=client,
                                         log=lambda e: None))
    assert code == 422 and client.calls == []
    assert [a["reason"].split(":")[0] for a in out["attempts"]] == ["unsupported", "unsupported"]


def test_the_chain_skips_a_model_that_cannot_read_values_and_asks_the_next():
    client = Client({"alpha/extractions": (200, {"answers": {"who": {"type": "text", "value": "Paul", "p_null": 0}},
                                                 "usage": {"cost": 0.000001}})})
    code, out = run(structured.decisions({"state": STATE, "questions": {"who": READ["who"]}},
                                         chain=["nace/drex-max-v1.1", "liquid/d1.2"], key=key, client=client,
                                         log=lambda e: None))
    assert code == 200 and out["model"] == "liquid/d1.2" and out["answers"]["who"]["text"] == "Paul"
    assert out["attempts"][0]["reason"].startswith("unsupported") and len(client.calls) == 1


def test_liquids_own_api_takes_every_kind_and_the_media_as_they_are():
    client = Client({"api.liquid.ai": (200, {"answers": {"face": {"type": "box", "box": None, "found": 0.1}},
                                             "usage": {"input_tokens": 50}})})
    code, out = run(structured.decisions({"state": {}, "questions": {"face": {"type": "box"}, **MULTI},
                                          "media": [{"type": "image", "data": "iVBORw0K"},
                                                    {"type": "audio", "data": "data:audio/wav;base64,UklGRg=="}]},
                                         chain=["liquidai/d1.2"], key=key, client=client, log=lambda e: None))
    sent = client.calls[0]["json"]
    assert code == 200 and sent["questions"]["topics"]["multiple"] is True
    assert sent["images"] == ["data:image/png;base64,iVBORw0K"]
    assert sent["audio"] == ["data:audio/wav;base64,UklGRg=="] and "media" not in sent   # live API reads audio here only
    with pytest.raises(wd.Invalid, match="media 0"):
        wd.check_media([{"type": "video", "data": "x"}])


def test_samples_of_typed_answers_merge_by_kind():
    s1 = {"topics": {"type": "choice", "choices": ["a"], "probabilities": {"a": 0.9, "b": 0.4}},
          "n": {"type": "number", "number": 10, "interval": [0, 20]},
          "who": {"type": "text", "text": "Paul", "found": 0.9}}
    s2 = {"topics": {"type": "choice", "choices": ["a", "b"], "probabilities": {"a": 0.8, "b": 0.8}},
          "n": {"type": "number", "number": 14, "interval": [4, 30]},
          "who": {"type": "text", "text": "Paul", "found": 0.7}}
    s3 = {"topics": {"type": "choice", "choices": ["a"], "probabilities": {"a": 0.7, "b": 0.2}},
          "n": {"type": "number", "number": 12, "interval": [2, 22]},
          "who": {"type": "text", "text": "Paula", "found": 0.5}}
    m = structured.merge_answers([s1, s2, s3])
    assert m["topics"]["choices"] == ["a"] and m["topics"]["probabilities"]["b"] == pytest.approx(1.4 / 3)
    assert m["n"]["number"] == 12 and m["n"]["interval"] == [2, 24]
    assert m["who"]["text"] == "Paul" and m["who"]["agreement"] == pytest.approx(2 / 3)


def test_an_ambiguous_date_the_model_found_is_read_in_the_declared_order():
    """17/11: « 05/12/2026 » found (0.99) but left unread by d1.2 and d1.2-ultra."""
    text = wd.render_state({"message": "Payer avant le 05/12/2026."})
    i = text.index("05/12/2026")

    def extract(body):
        assert "order" not in json.dumps(body["fields"])
        return 200, {"answers": {"due": {"type": "date", "value": None, "span": [i, i + 10], "p_null": 0.01},
                                 "other": {"type": "date", "value": None, "span": [i, i + 10], "p_null": 0.01}},
                     "usage": {"cost": 0.000001}}
    client = Client({"alpha/extractions": extract})
    q = {"due": {"type": "date", "order": "dmy"}, "other": {"type": "date"}}
    code, out = run(structured.decisions({"state": {"message": "Payer avant le 05/12/2026."}, "questions": q},
                                         chain=["liquid/d1.2"], key=key, client=client, log=lambda e: None))
    assert code == 200 and out["answers"]["due"]["date"] == "2026-12-05" and out["answers"]["due"]["read_by"] == "walter"
    assert out["answers"]["other"]["date"] is None                  # no declared order: left as the model gave it
    with pytest.raises(wd.Invalid, match="order is one of"):
        wd.compile_questions({"d": {"type": "date", "order": "dd/mm"}})
    native = wd.plan("liquid", "liquidai/d1.2", q)["native"]
    assert native["due"] == {"type": "date"}                         # Walter's own field never reaches a provider
