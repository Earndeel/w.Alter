"""Liquid's own decision API, measured 17/11/2026 (bench/liquid_native_features.py): capabilities, transport fields
(images / audio), reported cost, native answer shapes, refusals by name, the preferred-route switch — offline."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm"))
import decision as wd  # noqa: E402
import structured  # noqa: E402
from test_gateway_structured import Client, key  # noqa: E402

PNG = "data:image/png;base64,AAAA"
WAV = "data:audio/wav;base64,BBBB"


def run(coro):
    return asyncio.run(coro)


def test_every_kind_is_carried_and_verified_on_the_d1_2_family_only():
    for m in ("liquidai/d1.2", "liquidai/d1.2-ultra"):
        cap = wd.capabilities("liquid", m)
        assert cap["verified"] is True
        assert cap["native"] >= {"noul", "choice", "score", "multiple", "text", "number", "date", "estimate", "spans",
                                 "box", "boxes"}
        assert cap["media"] == {"image", "audio"} and not cap["extract"] and not cap["emulate"]
        assert {"spoken_question", "document"} <= cap["refused"]
    old = wd.capabilities("liquid", "liquidai/d1-ultra")
    assert old["verified"] is False and "text" not in old["native"] and "audio" not in old["media"]


def test_audio_goes_in_the_audio_field_never_in_media_and_images_in_images():
    out = structured._liquid_media([{"type": "image", "data": PNG}, {"type": "audio", "data": WAV},
                                    {"type": "audio", "data": "QUJD"}])
    assert out == {"images": [PNG], "audio": [WAV, "data:audio/wav;base64,QUJD"]}
    assert "media" not in out


def reply(answers, usage=None):
    return (200, {"model": "d1.2-ultra", "answers": answers, "usage": usage or {"input_tokens": 100, "cost": 4.2e-06}})


def test_one_native_call_carries_judgements_values_and_the_reported_cost_is_used():
    ans = {"mail": {"type": "noul", "noul": 0.001},
           "who": {"type": "text", "text": "Paul Martin", "span": [3, 14], "found": 0.99},
           "amount": {"type": "number", "number": None, "unit": None, "text": "300 euros", "span": [20, 29], "found": 0.99},
           "tags": {"type": "choice", "choices": ["a", "b"], "probabilities": {"a": 0.96, "b": 0.99, "c": 0.01}},
           "n": {"type": "number", "number": 31, "interval": [28, 34], "unit": None}}
    client = Client({"api.liquid.ai": reply(ans)})
    qs = {"mail": {"type": "noul", "instructions": "mail ?"}, "who": {"type": "text", "instructions": "who"},
          "amount": {"type": "number", "instructions": "how much"},
          "tags": {"type": "choice", "multiple": True, "criteria": {"a": "", "b": "", "c": ""}},
          "n": {"type": "number", "instructions": "how many", "range": [0, 100], "step": 1}}
    logs = []
    code, out = run(structured.decisions({"state": {"m": "x"}, "questions": qs}, chain=["liquidai/d1.2-ultra"], key=key,
                                         client=client, log=logs.append))
    assert code == 200 and len(client.calls) == 1                       # ONE call, no Extractions route
    assert client.calls[0]["url"] == structured.LIQUID_SYSTEMONE
    assert set(client.calls[0]["json"]["questions"]) == set(qs)
    a = out["answers"]
    assert a["tags"]["probabilities"]["a"] + a["tags"]["probabilities"]["b"] > 1.5      # independent, not one option
    assert a["amount"]["number"] == 300 and a["amount"]["read_by"] == "walter"           # « 300 euros » read by Walter
    assert a["n"]["interval"] == [28, 34]
    assert logs[0]["cost_usd"] == pytest.approx(4.2e-06) and logs[0]["cost_status"] == "reported"


def test_images_and_audio_reach_the_right_fields():
    client = Client({"api.liquid.ai": reply({"q": {"type": "noul", "noul": 0.9}})})
    run(structured.decisions({"state": {"m": "x"}, "media": [{"type": "image", "data": PNG}, {"type": "audio", "data": WAV}],
                              "questions": {"q": {"type": "noul", "instructions": "ok"}}},
                             chain=["liquidai/d1.2"], key=key, client=client, log=lambda e: None))
    body = client.calls[0]["json"]
    assert body["images"] == [PNG] and body["audio"] == [WAV] and "media" not in body


def test_a_box_needs_exactly_one_image_and_is_refused_by_name_before_any_call():
    qs = {"red": {"type": "box", "instructions": "the red square"}}
    for media in ([], [{"type": "image", "data": PNG}] * 2):
        client = Client({})
        code, out = run(structured.decisions({"state": {"m": "x"}, "media": media, "questions": qs},
                                             chain=["liquidai/d1.2-ultra"], key=key, client=client, log=lambda e: None))
        assert code == 422 and client.calls == []
        assert "red (box: needs exactly one image" in out["attempts"][0]["reason"]
    assert wd.plan("liquid", "liquidai/d1.2", qs, [{"type": "image", "data": PNG}])["native"] == qs


def test_a_spoken_question_and_documents_are_refused_by_name():
    with pytest.raises(wd.Invalid, match="instructions must be text"):
        wd.compile_questions({"q": {"type": "noul", "instructions": {"type": "audio", "data": WAV}}})
    with pytest.raises(wd.Invalid, match="media 0"):
        wd.check_media([{"type": "document", "data": "data:application/pdf;base64,JVBERi0="}])


def test_native_box_answers_keep_liquids_shape():
    box = {"top": 0.1, "bottom": 0.27, "left": 0.07, "right": 0.23}
    ans = {"red": {"type": "boxes", "boxes": [{"box": box, "found": 1, "confidence": 1}], "count": 1, "at_least": False,
                   "presence": [1, 0]}}
    client = Client({"api.liquid.ai": reply(ans)})
    code, out = run(structured.decisions(
        {"state": {"m": "x"}, "media": [{"type": "image", "data": PNG}],
         "questions": {"red": {"type": "boxes", "instructions": "every red square", "max": 4}}},
        chain=["liquidai/d1.2-ultra"], key=key, client=client, log=lambda e: None))
    assert code == 200 and out["answers"]["red"]["boxes"][0]["box"] == box


class Conn:
    """Stands in for the catalog connection: the decision offers that exist (OpenRouter's resale of d1.2)."""
    def __init__(self, offers):
        self.offers = offers

    def execute(self, sql, params=()):
        class R:
            def __init__(s, rows): s.rows = rows
            def fetchall(s): return s.rows
        return R([{"offer_key": o} for o in self.offers if o in (params[0] if params else ())])


def test_the_native_route_is_a_switch_of_decision_typed_not_the_default():
    from serve import intent
    conn = Conn(["liquid/d1.2-ultra", "liquid/d1.2"])
    assert intent._typed(conn, "nace/drex-max-v1.1", {}) == ("liquid/d1.2-ultra",)          # today's default
    native = {"typed": list(intent.NATIVE_TYPED)}
    # native first, the OpenRouter resale of the same model right behind it as failover
    assert intent._typed(conn, "nace/drex-max-v1.1", native) == ("liquidai/d1.2-ultra", "liquid/d1.2-ultra")
    assert intent._typed(Conn([]), "nace/drex-max-v1.1", native) == ()
    assert intent._typed(conn, "nace/drex-max-v1.1", {"typed": []}) == ()


def test_numbers_found_but_unread_are_read_by_walter_on_the_native_route():
    q = {"n": {"type": "number", "instructions": "how much"}}
    for text, want in (("300 euros", 300), ("1 450 €", 1450), ("89,90 €", 89.9)):
        got = wd.finish(q, {"n": {"type": "number", "number": None, "text": text, "found": 0.99}})["n"]
        assert got["number"] == want and got["read_by"] == "walter"
    nothing = {"n": {"type": "number", "number": None, "text": None, "found": 0.0}}
    assert wd.finish(q, nothing) == nothing
