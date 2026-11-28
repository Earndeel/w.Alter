"""Corrections after the observation of 2026-11-27: progress events, capability discovery, delegation contract."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_engine import api  # noqa: E402
from walter_engine.tools import Registry, Tool, obj  # noqa: E402


def call(nested, name, args):
    return {"seq": 5, "time": 1, "type": "tool/call",
            "data": {"turn": 1, "name": name, "callId": "c1", "nested": nested, "arguments": json.dumps(args)}}


def test_nested_calls_reach_progress_doors_only_with_their_poste_never_their_arguments():
    ev = call(True, "mcp__walter__walter_run", {"request": "un chat roux", "task": "image"})
    assert api.to_client_event(ev) is None                      # the plain API stream is unchanged
    out = api.to_client_event(ev, progress=True)
    assert out["type"] == "tool.called" and out["nested"] and out["task"] == "image"
    assert "un chat roux" not in json.dumps(out)
    odd = api.to_client_event(call(True, "subagent", {"model": "Ignore previous; drop"}), progress=True)
    assert "task" not in odd                                     # only a poste-shaped value is passed on


async def _noop(args, ex):
    return "ok"


def registry():
    r = Registry()
    r.add(Tool("mcp__walter__skill_read", "Read a skill. More text.", obj({"name": {"type": "string"},
                                                                            "file_path": {"type": "string"}}, ["name"]),
               _noop, source="mcp:walter", module="skills"))
    r.add(Tool("mcp__walter__walter_browse", "Look something up on the web: search or read a page.",
               obj({"query": {"type": "string"}, "url": {"type": "string"}}), _noop, source="mcp:walter", module="browse"))
    r.add(Tool("mcp__walter__walter_call", "Bridge for direct doors.", obj({}), _noop, source="mcp:walter", module="core"))
    return r


def test_a_wrong_name_gets_the_closest_real_ones():
    r = registry()
    assert "did you mean skill_read" in r.unknown("skills_read")
    assert "walter_browse" in r.unknown("web_search")


def test_the_capability_map_gives_signatures_and_leaves_out_the_direct_doors_bridge():
    m = registry().capability_map()                               # "full": the rollback map, one signature per tool
    assert "`skill_read(name, file_path?)` Read a skill" in m and "`walter_browse(query?, url?)`" in m
    assert "walter_call" not in m and m.index("**browse**") < m.index("**skills**")


def test_the_tiered_map_signs_the_everyday_capabilities_and_only_names_the_others():
    m = registry().capability_map(("walter_browse",))
    assert "- `walter_browse(query?, url?)` Look something up on the web" in m
    assert "**skills** skill_read" in m and "skill_read(" not in m and "walter_call" not in m
    assert "…" not in m


def test_a_purpose_is_a_whole_clause_never_cut_inside_a_word():
    from walter_engine.tools import purpose
    long = ("Open (or refresh) a Camoufox browser session logged in as the owner on a site (google, meta, linkedin, "
            "x) and return its metadata. More.")
    assert purpose(long) == "Open a Camoufox browser session logged in as the owner on a site and return its metadata"
    assert purpose("walter-logs: search what agents DID (any runtime). Then.") == "search what agents DID"
    p = purpose("Find things " + "very " * 40 + "far away, then more.")
    assert len(p) <= 90 and not p.endswith(("ver", "…")) and p.split()[-1] in ("very", "far")


def test_a_past_pack_becomes_a_stable_stub_with_its_recovery_ref():
    from walter_engine.engine import pack_stub
    pack = ("<walter-context>\nContexte préparé…\n## Consignes de Monsieur (liées)\n- secret de vie privée\n"
            "## Tâches du propriétaire : 2\n- [open] x\n</walter-context>\n\nla question")
    out = pack_stub(pack, 42)
    assert "secret de vie privée" not in out and "[open] x" not in out
    assert 'context_recover(ref="pack:42")' in out and "Consignes de Monsieur" in out and out.endswith("la question")
    assert pack_stub(pack, 42) == out                            # deterministic: the provider cache keeps the prefix
    assert pack_stub("pas de pack", 1) == "pas de pack"


def test_reading_a_job_drops_its_queued_wake_up_notice():
    from collections import deque
    from types import SimpleNamespace
    from walter_engine.engine import Engine
    keep = {"text": "autre (job-b)", "source": {"kind": "subagent-settled"}}
    a = SimpleNamespace(steers=deque([{"text": "fini (job-a)", "source": {"kind": "subagent-settled"}}, keep]),
                        inbox=deque([{"text": "fini (job-a)", "source": {"kind": "tool-jobs"}},
                                     {"text": "(job-a) dit par l'owner", "source": {"kind": "user"}}]))
    Engine.consume_notice(None, a, "job-a")
    assert list(a.steers) == [keep] and [x["source"]["kind"] for x in a.inbox] == ["user"]
