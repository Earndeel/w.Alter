from __future__ import annotations

import io
import json

import pytest

from walter_router import db, intent


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
    monkeypatch.setattr(intent.collect, "_env_value", lambda name: "k")
    out = intent.classify(conn, "une pub vidéo")
    assert sent["model"] == "~typesafe/jev-latest" and "text_to_video" in sent["questions"]["task"]["criteria"]
    assert out["task"] == "text_to_video" and out["cost"] == 0.00005


def test_forwarding_router_model_is_refused(conn, monkeypatch):
    monkeypatch.setattr(intent, "urlopen", lambda req, timeout: _Resp(json.dumps(
        {"model": "typesafe/jev-router", "answers": {}}).encode()))
    monkeypatch.setattr(intent.collect, "_env_value", lambda name: "k")
    with pytest.raises(ValueError):
        intent.classify(conn, "x")
