"""27/11/2026 (Monsieur): the capability map shows a parameter's allowed values when its contract declares a short
closed set (the model guessed order='desc' from the bare name), nothing more."""
from walter_engine.tools import Registry, Tool


def tool(props, required=()):
    return Tool(name="mcp__walter__memory_events", description="Read events.", run=None,
                parameters={"type": "object", "properties": props, "required": list(required)})


def test_short_closed_sets_are_shown_others_stay_bare():
    sig = Registry().signature(tool({"text": {"type": "string"},
                                     "order": {"type": "string", "enum": ["newest", "oldest"]},
                                     "kind": {"enum": list("abcdefg")},                  # too many values
                                     "mode": {"enum": ["a-very-long-value", "b"]},       # a value too long
                                     "limit": {"type": "integer"}}))
    assert sig == "memory_events(text?, order?: newest|oldest, kind?, mode?, limit?)"


def test_a_required_closed_set_too():
    assert Registry().signature(tool({"depth": {"enum": ["D1", "D2"]}}, ["depth"])) == "memory_events(depth: D1|D2)"
