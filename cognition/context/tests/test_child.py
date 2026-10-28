"""context.build(scope=child) (P2-b): the pack of a delegated sub-agent, without a model call; sources fail open."""
from walter_context import child


def test_mission_carries_goal_geo_contract_budget_and_rules():
    b = child._mission({"goal": "Trouve 2 offres", "constraints": {"geo": {"zone": "Asok", "pays": "TH"}, "max": 2},
                        "output_schema": {"offers": []}, "budget": {"seconds": 300, "turns": 12}})
    assert "Trouve 2 offres" in b.text and "zone=Asok" in b.text and '"offers"' in b.text and "300 s" in b.text
    assert "inconnu" in b.text and b.layer == 0


def test_build_orders_layers_keeps_caller_context_and_survives_failing_sources(monkeypatch):
    monkeypatch.setattr(child, "_capabilities", lambda t: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(child, "_skills", lambda g: None)
    monkeypatch.setattr(child, "_thread", lambda s: None)
    monkeypatch.setattr(child, "_memory", lambda g: None)
    out = child.build({"goal": "g", "toolsets": ["walter-web"], "caller_context": "ctx de l'appelant"})
    ids = [b["id"] for b in out["summary"]["blocks"]]
    assert ids == ["mission", "caller"] and "ctx de l'appelant" in out["text"]
    assert out["summary"]["notes"] and out["summary"]["notes"][0].startswith("capabilities")


def test_toolsets_select_only_their_modules():
    assert child.TOOLSET_MODULES["walter-web"] == ["browse"] and "terminal" not in child.TOOLSET_MODULES
