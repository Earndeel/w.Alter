"""Contracts v1: validation, round trips, and the JSON Schemas generated from the same vocabularies."""
import json
from pathlib import Path

import pytest

from walter_context.plan import (CAPABILITIES, ContextPlan, ContractError, LEVELS, MemoryViewQuery, ModelProfile,
                                 PLAN_TO_LEVEL, SessionState, ThreadChoice, ThreadHint, schemas)

ROOT = Path(__file__).resolve().parents[1]


def plan(**kw):
    base = dict(turn_id="t1", thread=ThreadChoice(id="th-3", confidence=0.8), act="continue", level="L2",
                domains=["projects"], horizons=["day"], capabilities=["skills"],
                model_profile=ModelProfile(task="coding", level="L2"))
    base.update(kw)
    return ContextPlan(**base)


def test_plan_round_trip_and_closed_vocabularies():
    d = plan().to_dict()
    assert ContextPlan.from_dict(json.loads(json.dumps(d))) == plan()
    for bad in (dict(level="L5"), dict(act="maybe"), dict(domains=["projects", "projects"]),
                dict(capabilities=["teleport"]), dict(thread=ThreadChoice(id="x", new=True)),
                dict(thread=ThreadChoice(id=None, new=False)), dict(model_profile=ModelProfile(level="L4")),
                dict(fast_path="guess"), dict(turn_id="")):
        with pytest.raises(ContractError):
            plan(**bad).validate()


def test_lot1_plans_map_onto_context_levels():
    assert set(PLAN_TO_LEVEL.values()) <= set(LEVELS) and "L4" not in PLAN_TO_LEVEL.values()


def test_session_state_thread_hint_and_view_query():
    assert SessionState("th-3", objective="ship lot B", constraints=["never publish"]).to_dict()["version"] == 1
    with pytest.raises(ContractError):
        SessionState("th-3", refs="call_1").validate()
    assert ThreadHint("s", "t", None, True, 0.4).to_dict()["new"]
    with pytest.raises(ContractError):
        ThreadHint("s", "t", "th-1", True).validate()
    assert MemoryViewQuery("overview", key="project:walter-context").to_dict()["max_tokens"] == 800
    for bad in (dict(depth="all", key="k"), dict(depth="index"), dict(depth="index", domain="weather"),
                dict(depth="index", key="k", max_tokens=0)):
        with pytest.raises(ContractError):
            MemoryViewQuery(**bad).validate()


def test_schema_files_are_generated_from_the_code():
    for name, schema in schemas().items():
        on_disk = json.loads((ROOT / "contracts" / "schemas" / name).read_text())
        assert on_disk == schema, f"{name} is stale: python -m walter_context.plan --write"
    assert schemas()["context-plan.v2.json"]["properties"]["capabilities"]["items"]["enum"] == list(CAPABILITIES)


def test_v1_plan_search_reads_as_memory_and_web():
    """ContextPlan v2 (07/11): a traced v1 plan keeps its meaning; `search` is no longer a v2 value."""
    from walter_context.plan import ContextPlan, ContractError, PLAN_VERSION
    v1 = {"version": 1, "turn_id": "t", "thread": {"id": None, "new": True}, "act": "new", "level": "L0",
          "capabilities": ["tools", "search", "skills"]}
    p = ContextPlan.from_dict(v1)
    assert p.version == PLAN_VERSION == 2 and p.capabilities == ["tools", "memory", "web", "skills"]
    import pytest
    with pytest.raises(ContractError):
        ContextPlan.from_dict({**v1, "version": 2})
