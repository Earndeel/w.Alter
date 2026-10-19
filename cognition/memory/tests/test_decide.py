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
    import builtins
    real_import = builtins.__import__

    def no_router(name, *a, **k):
        if name.startswith("walter_router"):
            raise ImportError("router down")
        return real_import(name, *a, **k)

    monkeypatch.setattr(llm, "_ROUTER_CHAIN", None)
    monkeypatch.setattr(builtins, "__import__", no_router)
    assert llm.decide_chain() == llm.DECIDE_CHAIN


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
