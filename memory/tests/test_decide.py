"""llm.decide: decision-model chain (Mercury Decide free → Clef), privacy guard (no network)."""
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
    out = llm.decide({"text": "appelle le +33 6 12 34 56 78"}, {"a": {}}, processor="t", privacy_class="redacted_cloud")
    assert [m for m, _ in seen] == list(llm.DECIDE_CHAIN) and out["model"] == "cloudflare/clef"
    assert all("+33" not in text for _, text in seen)


def test_local_only_is_refused(monkeypatch):
    monkeypatch.setattr(llm, "_log", lambda **row: None)
    with pytest.raises(llm.PrivacyRefused):
        llm.decide({"text": "x"}, {}, processor="t", privacy_class="local_only")
