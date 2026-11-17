"""Walter Decision 2.0 (2026-11-17): modules declare their decision signals in their own folder (contract key
`decisions`); Core discovers them and checks the envelope; one invalid file never takes the others down."""
import json
import subprocess

import pytest

from walter_platform import decisions

GOOD = {"occasions": ["turn"], "layer": "inference", "question": {"type": "noul", "instructions": "Work?"},
        "use": "the run plane opens a task", "consumers": ["memory.runs"], "since": "2026-11-17"}


def test_an_envelope_outside_the_contract_is_named():
    assert decisions.check_signal("work", GOOD) is GOOD
    for bad, why in ((dict(GOOD, occasions=["lunch"]), "occasions"), (dict(GOOD, layer="guess"), "layer"),
                     (dict(GOOD, use="x"), "use"), (dict(GOOD, when=["Bad Fact"]), "when"),
                     (dict(GOOD, options_from="threads"), "options_from goes with a choice"),
                     (dict(GOOD, extra=1), "unknown keys"), (dict(GOOD, consumers=["Memory"]), "consumers")):
        with pytest.raises(ValueError, match=why):
            decisions.check_signal("work", bad)
    with pytest.raises(ValueError, match="signal name"):
        decisions.check_signal("Work-1", GOOD)


def test_a_file_gives_global_ids(tmp_path):
    f = tmp_path / "decisions.json"
    f.write_text(json.dumps({"version": 1, "signals": {"work": GOOD}}))
    assert decisions.read(f, "memory")[0]["id"] == "memory.work"
    f.write_text(json.dumps({"version": 2, "signals": {"work": GOOD}}))
    with pytest.raises(ValueError, match="version"):
        decisions.read(f, "memory")


def test_the_live_registry_composes_every_module_and_reports_problems_apart():
    out = decisions.collect()
    ids = {s["id"] for s in out["signals"]}
    assert {"context.act", "context.plan", "router.tier", "memory.work", "memory.action"} <= ids
    assert out["problems"] == [] and len(out["hash"]) == 16
    assert {s["module"] for s in out["sources"]} >= {"context", "memory", "router"}
    turn = decisions.collect(occasion="turn")
    assert all("turn" in s["occasions"] for s in turn["signals"]) and turn["hash"] == out["hash"]


def test_the_command_is_what_walter_llm_reads():
    r = subprocess.run(["walter", "decisions", "--occasion", "incoming"], capture_output=True, text=True, timeout=60)
    data = json.loads(r.stdout)
    assert r.returncode == 0 and {s["id"] for s in data["signals"]} >= {"memory.action", "memory.deadline"}
