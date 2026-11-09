"""llm.decide: decision-model chain (Walter Router's, else Mercury Decide free → Clef), privacy guard (no network)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import llm  # noqa: E402


def test_falls_back_to_next_model_and_redacts(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "_log", lambda **row: None)

    def once(model, state, questions, timeout):
        seen.append((model, state["text"]))
        if model.startswith("inception/"):
            raise RuntimeError("HTTP 503")
        return {"answers": {"a": {"choice": "x"}}, "cost_usd": 0, "input_tokens": 10}, "cloudflare"

    monkeypatch.setattr(llm, "_decide_once", once)
    monkeypatch.setattr(llm, "decide_chain", lambda: llm.DECIDE_CHAIN)
    out = llm.decide({"text": "appelle le +33 6 12 34 56 78"}, {"a": {}}, processor="t", privacy_class="redacted_cloud")
    assert [m for m, _ in seen] == list(llm.DECIDE_CHAIN) and out["model"] == "cloudflare/clef"
    assert all("+33" not in text for _, text in seen)


def test_local_only_is_refused(monkeypatch):
    monkeypatch.setattr(llm, "_log", lambda **row: None)
    with pytest.raises(llm.PrivacyRefused):
        llm.decide({"text": "x"}, {}, processor="t", privacy_class="local_only")


def test_chain_falls_back_when_router_unavailable(monkeypatch):
    """The router is reached through its `walter-router` command only; when it fails, the static chain is used."""
    import subprocess

    def router_down(cmd, *a, **k):
        assert cmd[:2] == ["walter-router", "decision-chain"]
        raise FileNotFoundError("walter-router")

    monkeypatch.setattr(llm, "_ROUTER_CHAIN", None)
    monkeypatch.setattr(subprocess, "run", router_down)
    assert llm.decide_chain() == llm.DECIDE_CHAIN


def test_chain_comes_from_the_router_command(monkeypatch):
    import subprocess

    class Done:
        stdout = '{"chain": ["vendor/best", "inception/mercury-decide:free"]}'

    monkeypatch.setattr(llm, "_ROUTER_CHAIN", None)
    monkeypatch.setattr(subprocess, "run", lambda cmd, *a, **k: Done())
    assert llm.decide_chain() == ("vendor/best", "inception/mercury-decide:free")


def test_decide_uses_router_chain(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "_log", lambda **row: None)
    monkeypatch.setattr(llm, "decide_chain", lambda: ("typesafe/jev-x", "cloudflare/clef"))
    monkeypatch.setattr(llm, "account_balance", lambda: 100.0)

    def once(model, state, questions, timeout):
        seen.append(model)
        return {"answers": {"a": {"choice": "x"}}, "cost_usd": 0, "input_tokens": 1}, "openrouter"

    monkeypatch.setattr(llm, "_decide_once", once)
    llm.decide({"text": "x"}, {"a": {}}, processor="t", privacy_class="cloud_allowed")
    assert seen == ["typesafe/jev-x"]


def test_samples_are_averaged_and_a_failed_sample_is_dropped(monkeypatch):
    """samples=3 (preflight 2026-11-09): one model asked 3 times in parallel, answers averaged; a sample that fails is
    dropped, the decision stands on the others; only when all fail does the next model get asked."""
    monkeypatch.setattr(llm, "_log", lambda **row: None)
    draws = iter([{"m": {"type": "noul", "noul": 0.4},
                   "p": {"type": "choice", "choice": "none", "confidence": 0.5,
                         "probabilities": {"none": 0.55, "memory": 0.45}}},
                  {"m": {"type": "noul", "noul": 0.7},
                   "p": {"type": "choice", "choice": "memory", "confidence": 0.6,
                         "probabilities": {"none": 0.3, "memory": 0.7}}},
                  RuntimeError("HTTP 502")])
    import threading
    lock = threading.Lock()

    def once(model, state, questions, timeout):
        with lock:
            d = next(draws)
        if isinstance(d, Exception):
            raise d
        return {"answers": d, "cost_usd": 0, "input_tokens": 10}, "openrouter"

    monkeypatch.setattr(llm, "_decide_once", once)
    out = llm.decide({"text": "x"}, {}, processor="t", privacy_class="cloud_allowed", models=("a/b",), samples=3)
    a = out["answers"]
    assert out["samples"] == 2 and out["model"] == "a/b"
    assert a["m"]["noul"] == pytest.approx(0.55)
    assert a["p"]["choice"] == "memory" and a["p"]["probabilities"]["memory"] == pytest.approx(0.575)
    assert a["p"]["confidence"] == pytest.approx(0.3) and a["p"]["agreement"] == 0.5


def test_merge_is_deterministic_on_ties_and_one_sample_is_returned_as_is():
    one = {"p": {"type": "choice", "choice": "a", "confidence": 0.9, "probabilities": {"a": 0.5, "b": 0.5}}}
    assert llm.merge_answers([one, one])["p"]["choice"] == "a"
    assert llm.merge_answers([one])["p"]["agreement"] == 1.0
