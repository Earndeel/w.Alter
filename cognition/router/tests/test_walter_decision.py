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
     "extensive": {"type": "noul", "instructions": "Several sources?"},
     "note": {"type": "text"}}


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
    c = wd.compile_questions({**Q, "note": {"type": "text", "instructions": "other"}})[1]
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
