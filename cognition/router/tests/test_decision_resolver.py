"""Decision Resolver (§6, 2026-11-17): answers of one decision resolved against the relations modules declare.
Deterministic, no model. The relations here are the ones declared in production (Context, Memory manifests)."""
import json
import subprocess
import sys
from pathlib import Path

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
import resolver  # noqa: E402

# the relations come through Core's declared interface (`walter decisions`), never from another module's folder
REL = [r for r in json.loads(subprocess.run(["walter", "decisions"], capture_output=True, text=True, check=True,
                                            timeout=60).stdout).get("relations", [])
       if r.get("module") in ("context", "memory")]
ASKED = ["context.act", "context.thread", "context.plan", "context.extensive", "context.needs", "memory.resume"]


def needs(**p):
    return {"type": "choice", "choices": [k for k, v in p.items() if v >= 0.5], "probabilities": p}


def choice(c, conf, **p):
    return {"choice": c, "confidence": conf, "probabilities": p or {c: conf}}


def base(**over):
    a = {"context.act": choice("continue", 0.9), "context.thread": choice("t-1", 0.8),
         "context.plan": choice("thread", 0.85, thread=0.85, thread_and_memory=0.1),
         "context.extensive": {"noul": 0.2}, "context.needs": needs(memory=0.1, web=0.2), "memory.resume": {"noul": 0.3}}
    a.update(over)
    return a


def test_coherent_answers_pass_through_untouched():
    a = base()
    r = resolver.resolve(a, REL, asked=ASKED)
    assert r["signals"] == a and not r["changed"] and not r["conflicts"] and not r["missing"]


def test_a_real_conflict_is_settled_by_the_declared_rule_with_provenance():
    a = base(**{"context.needs": needs(memory=0.92, web=0.1)})            # sure: memory; sure: the thread suffices
    r = resolver.resolve(a, REL, asked=ASKED)
    assert r["signals"]["context.plan"]["choice"] == "thread_and_memory"
    assert r["conflicts"][0]["relation"] == "context.needs_memory_plan" and r["conflicts"][0]["settled"] == "if"
    ch = r["changed"]["context.plan"]
    assert ch["was"]["choice"] == "thread" and ch["by"] == ["context.needs_memory_plan"]
    assert a["context.plan"]["choice"] == "thread"                        # the models' answers are never modified


def test_a_strict_rule_holds_even_when_its_side_is_the_less_sure():
    a = base(**{"context.needs": needs(memory=0.55)})                     # memory barely, plan sure
    r = resolver.resolve(a, REL, asked=ASKED)
    assert r["signals"]["context.plan"]["choice"] == "thread_and_memory"
    assert r["uncertain_relations"] and not r["conflicts"]                # an uncertainty, not a conflict


def test_a_dependency_sets_aside_an_answer_that_means_nothing_here():
    a = base(**{"context.plan": choice("none", 0.9), "context.extensive": {"noul": 0.8}})
    r = resolver.resolve(a, REL, asked=ASKED)
    assert r["signals"]["context.extensive"] is None
    assert r["set_aside"][0]["signal"] == "context.extensive"


def test_the_rule_then_the_dependency_settle_in_order():
    # memory needed + plan none → plan becomes thread_and_memory, so extensive now counts
    a = base(**{"context.needs": needs(memory=0.9), "context.plan": choice("none", 0.9), "context.extensive": {"noul": 0.8}})
    r = resolver.resolve(a, REL, asked=ASKED)
    assert r["signals"]["context.plan"]["choice"] == "thread_and_memory" and r["signals"]["context.extensive"]["noul"] == 0.8


def test_a_certain_fact_fills_an_answer_no_model_gave_and_is_never_changed():
    a = base(**{"context.needs": needs(memory=0.1, web=0.9)})
    r = resolver.resolve(a, REL, facts={"anchor.memory"}, asked=ASKED)
    assert "memory" in r["signals"]["context.needs"]["choices"] and "web" in r["signals"]["context.needs"]["choices"]
    a2 = base()
    a2.pop("context.needs")
    r2 = resolver.resolve(a2, REL, facts={"anchor.memory"}, asked=ASKED)
    assert r2["signals"]["context.needs"]["choices"] == ["memory"]


def test_a_reporting_relation_changes_nothing_but_says_conflict_or_uncertainty():
    sure = resolver.resolve(base(**{"context.act": choice("new", 0.9)}), REL, asked=ASKED)
    assert sure["signals"]["context.thread"]["choice"] == "t-1"
    assert [c["relation"] for c in sure["conflicts"]] == ["context.new_subject_new_thread"]
    unsure = resolver.resolve(base(**{"context.act": choice("new", 0.9), "context.thread": choice("t-1", 0.35)}),
                              REL, asked=ASKED)
    assert unsure["signals"]["context.thread"]["choice"] == "t-1" and unsure["uncertain_relations"]
    both = resolver.resolve(base(**{"context.act": choice("new", 0.8), "memory.resume": {"noul": 0.9}}), REL, asked=ASKED)
    assert {c["relation"] for c in both["conflicts"]} >= {"memory.resume_not_new_subject"}


def test_missing_and_uncertain_are_said_never_guessed():
    a = base(**{"context.needs": needs(memory=0.9)})
    a["context.plan"] = None                                              # asked, no answer (unavailable)
    r = resolver.resolve(a, REL, asked=ASKED, required=["context.plan"])
    assert r["signals"]["context.plan"] is None
    assert {m["signal"] for m in r["missing"]} >= {"context.plan"}
    low = resolver.resolve(base(**{"context.act": choice("continue", 0.41)}), REL, asked=ASKED)
    assert {"signal": "context.act", "confidence": 0.41} in low["uncertain"]


def test_relations_about_signals_this_decision_did_not_ask_are_not_applied():
    a = {"context.needs": needs(memory=0.9), "context.plan": choice("none", 0.9)}
    r = resolver.resolve(a, REL, asked=["context.needs"])                 # a reassessment that only asked needs
    assert not r["changed"] and r["signals"] == a


def test_brief_names_without_values():
    r = resolver.resolve(base(**{"context.needs": needs(memory=0.92)}), REL, asked=ASKED)
    b = resolver.brief(r)
    assert b["changed"] == {"context.plan": ["context.needs_memory_plan"]} and "conflicts" in b
    assert "thread_and_memory" not in json.dumps(b)


def test_relations_chain_until_stable_a_named_project_brings_memory_then_the_plan_follows():
    a = base(**{"context.needs": needs(memory=0.1, web=0.8), "context.plan": choice("last_exchange", 0.9)})
    r = resolver.resolve(a, REL, facts={"anchor.memory"}, asked=ASKED)
    assert "memory" in r["signals"]["context.needs"]["choices"]
    assert r["signals"]["context.plan"]["choice"] == "thread_and_memory"
    assert r["changed"]["context.plan"]["by"] == ["context.needs_memory_plan"]
