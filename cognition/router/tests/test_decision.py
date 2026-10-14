"""AA Decision Index (2026-10-13): page parsing, identities, decision chain order."""
import json

from walter_router import collect, identity

ROWS = [{"slug": "typesafe_jev-1-13", "kind": "decisionModel", "name": "Jev 1.13", "hostName": "TypeSafe",
         "indexScore": 57.5, "costPerTaskUsd": 4.2e-05, "timePerTaskMs": 127, "scores": {"when2callAccuracy": 81}},
        {"slug": "openai_gpt-6-luna-decisions", "kind": "decisionModel", "name": "GPT-6 Luna (Decisions)",
         "indexScore": 48.5, "costPerTaskUsd": 7.9e-05},
        {"slug": "anthropic_claude-haiku-5-5-low", "kind": "llm", "name": "Claude Haiku 5.5 (Low)", "indexScore": 60.6,
         "costPerTaskUsd": 0.000184},
        {"slug": "anthropic_claude-opus-5-5", "kind": "llm", "name": "Claude Opus 5.5 (Max, Default Fallback)",
         "indexScore": 79.0, "costPerTaskUsd": 0.0513}]


def test_rsc_page_is_decoded():
    payload = json.dumps('3a:["$","$L3e",null,{"contestants":' + json.dumps(ROWS) + '}]')[1:-1]
    page = f'<script>self.__next_f.push([1,"{payload}"])</script>'
    assert [r["slug"] for r in collect.aa_decision_rows(page)] == [r["slug"] for r in ROWS]


def test_rows_identities_and_costs():
    rows = {r["external_key"]: r for r in collect.parse_benchmarks("aa_decision", {"rows": ROWS})}
    jev = rows["typesafe_jev-1-13"]
    assert (jev["model_id"], jev["variant"], jev["task"]) == ("jev-1-13", "", "decision")
    assert round(jev["cost"]) == 42 and jev["cost_unit"] == "usd_per_1m_tasks"
    assert (rows["openai_gpt-6-luna-decisions"]["model_id"], rows["openai_gpt-6-luna-decisions"]["variant"]) == \
        ("gpt-6-luna-decisions", "")
    assert (rows["anthropic_claude-haiku-5-5-low"]["model_id"], rows["anthropic_claude-haiku-5-5-low"]["variant"]) == \
        ("claude-haiku-5-5", "low")
    assert rows["anthropic_claude-opus-5-5"]["variant"] == "max"


def test_namespace_registered():
    assert "aa_decision" in identity.BENCHMARK_NAMESPACES
