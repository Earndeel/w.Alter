"""SOCLE A6 (2026-11-11): skills postes name a Router task + tier only and reach a model through the gateway by poste."""
from __future__ import annotations

from walter_skills import config, postes


def test_shipped_postes_name_no_model_and_no_transport():
    for name, poste in (config.load().get("postes") or {}).items():
        for route in poste["routes"]:
            assert "model" not in route and "via" not in route, name
            assert route.get("level") in ("L1", "L2", "L3")


def test_ask_goes_to_the_gateway_by_poste_and_never_launches_codex(monkeypatch):
    seen = []

    def chat(messages, **kw):
        seen.append(kw)
        return {"content": '{"summary": "ok"}'}
    monkeypatch.setattr(postes.llm, "chat", chat)
    monkeypatch.setattr(postes.config, "poste", lambda name: [
        {"task": "general", "level": "L2", "budget": "recurring"},
        {"via": "codex", "model": "some-model"}])                    # a stale static route is ignored
    obj, route = postes.ask_json("editor", "prompt", require="summary")
    assert obj == {"summary": "ok"} and route == "router:general/L2"
    assert len(seen) == 1 and seen[0]["poste"] == "general/L2" and "model" not in seen[0]
    assert not hasattr(postes, "subprocess")


def test_failed_gateway_call_tries_the_next_route_then_says_none(monkeypatch):
    calls = []

    def chat(messages, **kw):
        calls.append(kw["poste"])
        raise RuntimeError("walter-llm unreachable")
    monkeypatch.setattr(postes.llm, "chat", chat)
    monkeypatch.setattr(postes.config, "poste", lambda name: [{"level": "L2"}, {"level": "L1"}])
    assert postes.ask("judge", "p") == (None, None)
    assert calls == ["general/L2", "general/L1"]
