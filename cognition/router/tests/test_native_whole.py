"""Préflight natif (18/11): a need's policy `assign: native_whole` sends the whole set in ONE call to the first model of
the chain that carries it all natively; a hedge only past `hedge_after_ms`; past `failover_after_ms` or on an error
the per-question split starts and the first COMPLETE answer wins. Offline (fake routes with delays)."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm"))
import decision as wd  # noqa: E402
import resolver  # noqa: E402
import structured  # noqa: E402
from test_gateway_structured import Resp, key  # noqa: E402

DREX, NATIVE, OR = "nace/drex-max-v1.1", "liquidai/d1.2-ultra", "liquid/d1.2-ultra"
QS = {"act": {"type": "choice", "criteria": {"new": "new", "continue": "continue"}},
      "needs": {"type": "choice", "multiple": True, "criteria": {"memory": "m", "web": "w", "browser": "b"}}}
SPANS = {"places": {"type": "spans", "instructions": "places named", "max": 4}}


def _answers(questions):
    out = {}
    for k, q in questions.items():
        t = q.get("type")
        if t == "noul":
            out[k] = {"type": "noul", "noul": 0.8}
        elif t == "spans":
            out[k] = {"type": "spans", "spans": [{"text": "Lyon", "found": 0.9}]}
        elif q.get("multiple"):
            out[k] = {"type": "choice", "choices": ["web"], "probabilities": {"memory": 0.1, "web": 0.9, "browser": 0.2}}
        else:
            opts = list(q.get("criteria") or q.get("options") or {"a": ""})
            out[k] = {"type": "choice", "choice": opts[0], "probabilities": {o: (0.9 if i == 0 else 0.1)
                                                                               for i, o in enumerate(opts)}}
    return out


class Routes:
    """A fake client: per host, a delay and a status; records the calls (host, questions)."""

    def __init__(self, **spec):
        self.spec, self.calls = spec, []

    async def post(self, url, headers=None, json=None, timeout=None):
        host = "liquid" if "api.liquid.ai" in url else "nace" if "nace" in url else \
            "extract" if "extractions" in url else "openrouter"
        self.calls.append((host, sorted((json or {}).get("questions") or (json or {}).get("fields") or {})))
        delay, status = self.spec.get(host, (0.0, 200))
        await asyncio.sleep(delay)
        if status >= 400:
            return Resp(status, {"error": {"code": "upstream"}})
        if host == "extract":
            return Resp(200, {"answers": {k: {"spans": [{"text": "Lyon", "found": 0.9}]} for k in json["fields"]},
                              "usage": {"cost": 1e-6}})
        return Resp(200, {"answers": _answers(json["questions"]), "usage": {"input_tokens": 100, "cost": 1e-6}})


def run(body, chain, client, policy, monkeypatch):
    monkeypatch.setattr(wd, "policy", lambda need: {**wd.DEFAULT_POLICY, **policy})
    structured._unavailable.clear()
    logs = []
    code, out = asyncio.run(structured.decisions({"state": {"m": "x"}, **body}, chain=chain, key=key, client=client,
                                                 log=logs.append))
    return code, out, logs


WHOLE = {"assign": "native_whole", "hedge_after_ms": 200, "failover_after_ms": 400}


def test_the_whole_set_goes_in_one_call_to_the_first_model_that_carries_it_natively(monkeypatch):
    client = Routes()
    code, out, _ = run({"questions": {**QS, **SPANS}}, [DREX, NATIVE, OR], client, WHOLE, monkeypatch)
    assert code == 200 and out["assign"] == "native_whole" and out["model"] == NATIVE
    assert client.calls == [("liquid", ["act", "needs", "places"])]               # Drex first in the chain, not asked
    assert out["answers"]["needs"]["probabilities"]["web"] == 0.9 and out["answers"]["places"]["spans"]


def test_without_the_policy_the_split_is_unchanged(monkeypatch):
    client = Routes()
    code, out, _ = run({"questions": QS}, [DREX, NATIVE], client, {}, monkeypatch)
    assert code == 200 and out["assign"] == "split" and {h for h, _ in client.calls} == {"nace"}


def test_a_hedge_only_when_the_first_call_is_late(monkeypatch):
    fast = Routes(liquid=(0.02, 200))
    run({"questions": QS, "samples": 2, "sampling": "first"}, [DREX, NATIVE], fast, WHOLE, monkeypatch)
    assert fast.calls == [("liquid", ["act", "needs"])]                            # answered before 200 ms: one call
    slow = Routes(liquid=(0.3, 200))
    code, out, logs = run({"questions": QS, "samples": 2, "sampling": "first"}, [DREX, NATIVE], slow,
                          {**WHOLE, "failover_after_ms": 2000}, monkeypatch)
    assert code == 200 and [h for h, _ in slow.calls] == ["liquid", "liquid"]     # the hedge, never Drex
    assert out["assign"] == "native_whole" and any(e.get("skipped") == "hedged" for e in logs)


def test_an_error_of_the_native_route_fails_over_to_the_split_at_once(monkeypatch):
    client = Routes(liquid=(0.0, 500))
    code, out, _ = run({"questions": QS}, [DREX, NATIVE], client, WHOLE, monkeypatch)
    assert code == 200 and out["assign"] == "split" and out["failover"] == "error" and out["model"] == DREX
    assert out["answers"]["needs"]["choices"] or out["answers"]["needs"].get("probabilities")   # emulated on Drex
    assert structured._unavailable.get(NATIVE)                                     # set aside a minute


def test_a_slow_native_route_lets_a_complete_split_answer_first(monkeypatch):
    client = Routes(liquid=(1.5, 200), nace=(0.02, 200))
    code, out, _ = run({"questions": QS}, [DREX, NATIVE], client, {**WHOLE, "failover_after_ms": 100}, monkeypatch)
    assert code == 200 and out["assign"] == "split" and out["failover"] == "slow"


def test_an_incomplete_split_never_wins_the_race_against_the_native_call(monkeypatch):
    # the split can read the judgements (Drex) but its spans route fails: the native call, slower, answers in full
    client = Routes(liquid=(0.3, 200), nace=(0.01, 200), extract=(0.0, 500))
    code, out, _ = run({"questions": {**QS, "places": {**SPANS["places"]}}}, [DREX, NATIVE, OR], client,
                       {**WHOLE, "failover_after_ms": 50}, monkeypatch)
    assert code == 200 and out["assign"] == "native_whole" and "native answered first" in out["failover"]
    assert "unavailable" not in out and out["answers"]["places"]["spans"]


def test_no_native_model_in_the_chain_keeps_the_split(monkeypatch):
    client = Routes()
    code, out, _ = run({"questions": QS}, [DREX], client, WHOLE, monkeypatch)
    assert code == 200 and out["assign"] == "split" and "failover" not in out


def test_has_any_holds_when_one_option_does():
    ans = {"c.personal": {"probabilities": {"location": 0.9, "people": 0.1, "history": 0.2}}}
    cond = {"signal": "c.personal", "has_any": ["people", "history"]}
    assert resolver.evaluate(cond, ans, set())[0] is False
    ans["c.personal"]["probabilities"]["history"] = 0.7
    assert resolver.evaluate(cond, ans, set()) == (True, 0.7)
    assert resolver.evaluate({"signal": "c.other", "has_any": ["x"]}, ans, set()) == (None, None)
    rel = [{"id": "c.r", "type": "implies", "if": cond, "then": {"signal": "c.needs", "has": "memory"}, "prefer": "if"}]
    out = resolver.resolve({**ans, "c.needs": {"probabilities": {"memory": 0.2, "web": 0.8}}}, rel, set())
    assert out["signals"]["c.needs"]["probabilities"]["memory"] >= 0.5


AUDIO = [{"type": "audio", "data": "data:audio/ogg;base64,AAAA"}]


def test_native_down_with_audio_falls_back_to_the_text_when_the_need_allows_it(monkeypatch):
    # audio: only Liquid's own API reads it; it fails → the split asks the others on the text, says what it left out
    client = Routes(liquid=(0.0, 500))
    code, out, _ = run({"questions": QS, "media": AUDIO}, [DREX, NATIVE, OR], client,
                       {**WHOLE, "media_fallback": "text"}, monkeypatch)
    assert code == 200 and out["assign"] == "split" and out["media_dropped"] == ["audio"]
    assert {h for h, _ in client.calls} >= {"liquid", "nace"}
    strict = Routes(liquid=(0.0, 500))
    code, out, _ = run({"questions": QS, "media": AUDIO}, [DREX, NATIVE, OR], strict, WHOLE, monkeypatch)
    assert code != 200 or "media_dropped" not in out                               # without the policy: never dropped


def test_past_settle_the_judgements_stand_without_late_optional_readings(monkeypatch):
    # Liquid slow on both its routes (18/11 16:43): the native call and the Extractions route both lag; Drex has the
    # judgements at once → past settle_after_ms the plan gets them, the passages are said late, not waited for
    import time as _t
    sigs = [{"id": "c.act", "module": "c", "name": "act", "occasions": ["turn"], "layer": "inference",
             "question": QS["act"], "use": "u", "required": True},
            {"id": "c.needs", "module": "c", "name": "needs", "occasions": ["turn"], "layer": "inference",
             "question": QS["needs"], "use": "u"},
            {"id": "c.places", "module": "c", "name": "places", "occasions": ["turn"], "layer": "observation",
             "question": SPANS["places"], "use": "u"}]
    monkeypatch.setattr(wd, "policy", lambda need: {**wd.DEFAULT_POLICY, **WHOLE, "failover_after_ms": 50,
                                                    "settle_after_ms": 250})
    structured._unavailable.clear()
    wd._COMPOSED.clear()
    client, logs = Routes(liquid=(1.0, 200), nace=(0.01, 200), extract=(1.0, 200)), []
    t0 = _t.perf_counter()
    code, out = asyncio.run(structured.decisions({"state": {"m": "x"}, "occasion": "turn"}, chain=[DREX, NATIVE, OR],
                                                 key=key, client=client, log=logs.append,
                                                 signals={"hash": "h", "signals": sigs}))
    took = _t.perf_counter() - t0
    assert code == 200 and out["assign"] == "split" and took < 0.6
    assert out["trace"]["unavailable"]["c.places"].startswith("late") and out["signals"]["c.act"]
    assert any(e.get("skipped") == "late" for e in logs)


def test_a_required_part_is_waited_for_past_settle(monkeypatch):
    client = Routes(liquid=(0.0, 500), nace=(0.4, 200))
    code, out, _ = run({"questions": QS}, [DREX, NATIVE], client,
                       {**WHOLE, "failover_after_ms": 50, "settle_after_ms": 100}, monkeypatch)
    assert code == 200 and "unavailable" not in out and out["answers"]["needs"]
