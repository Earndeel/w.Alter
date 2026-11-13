from __future__ import annotations

import io
import json

import pytest

from walter_router.store import db
from walter_router.serve import intent


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def conn():
    with db.connect() as c:
        yield c
        c.rollback()


def test_classify_reads_every_answer(conn, monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent.update(json.loads(req.data))
        answers = {name: {"choice": next(iter(q["criteria"])), "confidence": 0.9,
                          "probabilities": {next(iter(q["criteria"])): 0.9}} for name, q in sent["questions"].items()}
        answers["task"]["choice"] = "text_to_video"
        return _Resp(json.dumps({"model": "typesafe/jev-1.13-x", "answers": answers,
                                 "usage": {"cost": 0.00005}}).encode())

    monkeypatch.setattr(intent, "urlopen", fake_urlopen)
    monkeypatch.setattr(intent.instance, "secret_value", lambda name: "k")
    out = intent.classify(conn, "une pub vidéo", models=(intent.MODEL,))
    assert sent["model"] == "~typesafe/jev-latest" and "text_to_video" in sent["questions"]["task"]["criteria"]
    assert out["task"] == "text_to_video" and out["cost"] == 0.00005


def test_forwarding_router_model_is_refused(conn, monkeypatch):
    monkeypatch.setattr(intent, "urlopen", lambda req, timeout: _Resp(json.dumps(
        {"model": "typesafe/jev-router", "answers": {}}).encode()))
    monkeypatch.setattr(intent.instance, "secret_value", lambda name: "k")
    with pytest.raises(ValueError):
        intent.classify(conn, "x", models=(intent.MODEL,))


def test_nace_models_are_called_on_nace_and_their_answer_accepted(conn, monkeypatch):
    """2026-11-13: Drex Max 1.1 pinned on provider nace → Nace systemone, never OpenRouter."""
    sent = []

    def fake_urlopen(req, timeout):
        sent.append((req.full_url, json.loads(req.data)["model"]))
        body = json.loads(req.data)
        answers = {n: {"choice": next(iter(q["criteria"])), "confidence": 0.9, "probabilities": {}}
                   for n, q in body["questions"].items()}
        return _Resp(json.dumps({"model": "drex-max-v1.1", "answers": answers}).encode())

    monkeypatch.setattr(intent, "urlopen", fake_urlopen)
    monkeypatch.setattr(intent.instance, "secret_value", lambda name: "k")
    out = intent.classify(conn, "une pub vidéo", models=("nace/drex-max-v1.1",))
    assert sent == [(intent.NACE_SYSTEMONE, "drex-max-v1.1")] and out["model"] == "nace/drex-max-v1.1"


def test_chain_falls_back_to_the_next_decision_model(conn, monkeypatch):
    """best_first (2026-10-14): the cycle's best (paid, OpenRouter) fails, e.g. HTTP 402 → Clef on Workers AI, free
    and off OpenRouter (Mercury Decide free, withdrawn by OpenRouter, left the chain on 2026-11-13)."""
    calls = []
    chain = intent.chain(conn)
    assert "inception/mercury-decide:free" not in chain and "cloudflare/clef" in chain

    def answer(payload):
        return {n: {"choice": next(iter(q["criteria"])), "confidence": 0.9, "probabilities": {}}
                for n, q in payload["questions"].items()}

    def fake_cloudflare(model, payload, timeout):
        calls.append(model)
        return {"answers": answer(payload), "model": model}

    def fake_urlopen(req, timeout):
        calls.append(json.loads(req.data)["model"])
        raise RuntimeError("HTTP Error 402: Payment Required")

    monkeypatch.setattr(intent, "_cloudflare", fake_cloudflare)
    monkeypatch.setattr(intent, "urlopen", fake_urlopen)
    monkeypatch.setattr(intent.instance, "secret_value", lambda name: "k")
    out = intent.classify(conn, "une pub vidéo")
    assert calls[-1] == "cloudflare/clef" and out["model"] == "cloudflare/clef"
    if chain[0] != "cloudflare/clef":
        assert out["fallback_errors"]
