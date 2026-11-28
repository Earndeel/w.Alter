"""A decision reports its first executable provider as subscriptions/quotas reorder routes."""
from types import SimpleNamespace

import pytest

from walter_router.serve import agent_view, named, routes


@pytest.mark.parametrize("providers", [
    ["claude-pro", "openrouter", "kie"],
    ["openrouter", "claude-pro", "kie"],
    ["future-subscription", "kie"],
    [],
])
def test_ordinary_decision_provider_follows_effective_order(monkeypatch, providers):
    conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: {
        "interface": "chat", "requirements": {}, "modes": []}))
    monkeypatch.setattr(routes.execution, "routes", lambda *a, **k: [
        {"provider": p, "model": "same-model"} for p in providers])
    d = routes.with_execution(conn, {"task": "general", "level": "L3",
                                    "model_id": "same-model", "provider": "kie"})
    assert d["provider"] == (providers[0] if providers else None)
    view = agent_view.view(d)
    assert view.get("provider") == d["provider"]
    if providers:
        assert view["provider"] == view["execution"][0]["provider"]


@pytest.mark.parametrize("restriction", [None, "kie"])
def test_named_model_summary_keeps_strict_provider_restriction(monkeypatch, restriction):
    conn = SimpleNamespace()
    monkeypatch.setattr(named, "resolve", lambda *a: ("same-model", ""))
    monkeypatch.setattr(named.sel, "latest_snapshots", lambda *a: {})
    monkeypatch.setattr(named.sel, "load_offers", lambda *a: {"same-model": [
        {"provider": p, "interface": "chat"} for p in ["claude-pro", "kie"]]})
    monkeypatch.setattr(named.execution, "routes", lambda *a: [
        {"provider": p, "model": "same-model"} for p in ["claude-pro", "kie"]])
    d = named.named(conn, "same-model", restriction)
    assert d["provider"] == d["execution"][0]["provider"] == (restriction or "claude-pro")
    assert d["named"]["provider"] == restriction
    if restriction:
        assert all(r["provider"] == restriction for r in d["execution"])
