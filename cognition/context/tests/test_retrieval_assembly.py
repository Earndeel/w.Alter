"""Step D: retrieval asks only what the plan needs, assembly orders stable → volatile and counts what is injected."""
import sys
import types

import pytest

from walter_context import retrieval
from walter_context.assembly import pack
from walter_context.plan import ContextPlan, ThreadChoice


def plan(level, thread="subject:abc", caps=("tools",), domains=()):
    return ContextPlan(turn_id="t", thread=ThreadChoice(id=thread), act="continue", level=level,
                       capabilities=list(caps), domains=list(domains))


@pytest.fixture
def sources(monkeypatch):
    calls = []
    monkeypatch.setattr(retrieval, "capabilities", lambda p: (calls.append("caps"), retrieval.Block("capabilities", 0, "M0 x10"))[1])
    monkeypatch.setattr(retrieval, "board", lambda *a: (calls.append("board"), retrieval.Block("subjects_board", 1, "- s1\n- s2"))[1])
    monkeypatch.setattr(retrieval, "tasks", lambda p: None)
    monkeypatch.setattr(retrieval, "experience", lambda p, m: None)
    views = types.SimpleNamespace(read=lambda q: (calls.append(("view", q["depth"])),
                                                  {"depth": "overview", "content": "Titre : X", "version": 3})[1])
    context = types.SimpleNamespace(get_context=lambda m, budget, include_profile, **kw: (calls.append(("memory", budget["knowledge"])),
                                                                                    {"text": "souvenirs", "trace": {"sections": {}}})[1])
    pkg = types.ModuleType("walter_memory")
    pkg.views, pkg.context = views, context
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.views", views)
    monkeypatch.setitem(sys.modules, "walter_memory.context", context)
    monkeypatch.setattr(retrieval, "recent", lambda key, native: retrieval.Block("recent_exchanges", 5, "Owner : oui", injected=not native))
    return calls


def test_l0_takes_capabilities_only(sources):
    blocks, notes = retrieval.gather(plan("L0"), "54 % de 89")
    assert [b.id for b in blocks] == ["capabilities", "now"] and sources == ["caps"] and not notes


def test_depth_and_memory_follow_the_level(sources):
    blocks, _ = retrieval.gather(plan("L2"), "et la suite ?")
    assert ("view", "overview") in sources and not any(c[0] == "memory" and c[1] for c in sources if isinstance(c, tuple))
    sources.clear()
    blocks, _ = retrieval.gather(plan("L4"), "tout ce qu'on a décidé")
    assert ("view", "synthesis") in sources and ("memory", 1200) in sources
    p = pack(plan("L4"), blocks)
    assert [b.layer for b in p.blocks] == sorted(b.layer for b in p.blocks)
    s = p.summary()
    assert s["tokens_session_layer"] > 0 and s["tokens_native_not_injected"] > 0       # native history: counted only
    assert "Owner : oui" not in p.text() and "souvenirs" in p.text() and "M0 x10" not in p.text()
    assert "M0 x10" in p.text(include_session_layer=True)


def test_a_failing_source_drops_only_its_block(sources, monkeypatch):
    def boom(*a):
        raise TimeoutError("views down")
    monkeypatch.setattr(retrieval, "board", boom)
    blocks, notes = retrieval.gather(plan("L2"), "et la suite ?")
    assert "subjects_board" not in [b.id for b in blocks] and notes and notes[0].startswith("board: TimeoutError")
    assert pack(plan("L2", thread=None), [], []).text() == ""


def test_shadow_report_compares_pack_and_current(tmp_path):
    import json
    from datetime import datetime, timezone
    from walter_context.shadow import report
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [{"plan": {"level": "L2", "thread": {"id": "subject:a"}, "fast_path": None}, "plan_ms": 700,
              "pack": {"tokens_per_message": 900, "tokens_session_layer": 680, "retrieval_ms": 40, "notes": []},
              "current": {"tokens": 500}},
             {"plan": {"level": "L1", "thread": {"id": "subject:a"}, "fast_path": "short_reply"}, "plan_ms": 1,
              "pack": {"tokens_per_message": 0, "tokens_session_layer": 680, "retrieval_ms": 2, "notes": ["board: X"]},
              "current": {"tokens": 0}},
             {"error": "boom"}]
    (tmp_path / f"preflight-{day}.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    r = report(tmp_path)
    assert r["messages"] == 2 and r["errors"] == 1 and r["levels"] == {"L2": 1, "L1": 1}
    assert r["tokens_per_message"]["walter_context_total"] == 900 and r["tokens_per_message"]["current_hook_total"] == 500
    assert r["nothing_injected"] == {"walter_context": 1, "current_hook": 1} and r["source_failures"] == {"board": 1}


def test_tool_cards_follow_the_plan(monkeypatch):
    """07/11: a web question gets the browse brief for this message; a plain one gets none."""
    from walter_context import retrieval
    from walter_context.plan import ContextPlan, ThreadChoice
    monkeypatch.setattr(retrieval, "_card", lambda m, ttl=600: f"### {m} brief")
    mk = lambda caps: ContextPlan(turn_id="t", thread=ThreadChoice(id=None, new=True), act="new", level="L0",
                                  capabilities=["tools", *caps])
    b = retrieval.tool_cards(mk(["web", "browser"]))
    assert b.layer == 4 and b.sources == ["browse", "computer"] and "browse brief" in b.text
    assert retrieval.tool_cards(mk([])) is None and retrieval.tool_cards(mk(["delegation"])) is None


def test_the_present_instant_is_in_every_pack_in_the_owner_zone(monkeypatch):
    """07/11: nothing gave the model the date; it ran `date` (one more step) and guessed the owner's zone."""
    from datetime import datetime, timezone
    import types, sys
    from walter_context import retrieval
    fake = types.SimpleNamespace(settings=lambda: {"periods": {"tz": "Asia/Bangkok"}})
    monkeypatch.setitem(sys.modules, "walter_memory.organic", fake)
    import walter_memory
    monkeypatch.setattr(walter_memory, "organic", fake, raising=False)
    b = retrieval.now(datetime(2026, 11, 7, 20, 4, tzinfo=timezone.utc))
    assert b.layer == 5 and b.text == ("Maintenant : dimanche 8 novembre 2026, 03:04 heure locale (Asia/Bangkok) ; "
                                       "2026-11-07 20:04 UTC.")
    assert b.tokens < 40


# --- lot C2 (2026-11-11): pack budget, board, freshness, tasks and experience --------------------------------------
def test_pack_stays_within_the_level_budget_and_records_every_cut():
    from walter_context.retrieval import Block
    blocks = [Block("subjects_board", 1, "Sujets :\n" + "\n".join(f"- s{i} " + "x" * 60 for i in range(20))),
              Block("session_state", 2, "État :\n" + "y" * 800),
              Block("memory", 4, "Mémoire :\n" + "\n".join("z" * 100 for _ in range(30))),
              Block("now", 5, "Maintenant : x")]
    p = pack(plan("L1"), blocks, budget=500)
    s = p.summary()
    assert s["tokens_per_message"] <= 500 and s["budget"] == 500
    assert [c["block"] for c in s["cuts"]][:1] == ["subjects_board"]          # least relevant first
    assert all(c["action"] in ("shrunk", "dropped") and c["to"] < c["from"] for c in s["cuts"])
    assert "Maintenant : x" in p.text()                                       # never cut
    assert "coupé : budget" in p.text() or any(c["action"] == "dropped" for c in s["cuts"])
    q = pack(plan("L4"), blocks)                                              # within budget: untouched
    assert q.summary()["cuts"] == [] and q.summary()["budget"] == retrieval.PACK["budget"]["L4"]


def test_board_keeps_the_plans_thread_and_recent_open_subjects_only(monkeypatch):
    from datetime import datetime, timezone
    at = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
    content = "\n".join([
        "- subject:a1 · Sujet ouvert récent — en_cours · 11/11 12:49",
        "- subject:a2 · Sujet terminé — fait · 11/11 12:00",
        "- subject:a3 · Sujet ancien ouvert — en_cours · 01/11 09:00",
        "- subject:mine · Le fil du plan — fait · 20/10 08:00",
        "- subject:a4 · Attend le propriétaire — attend_le_proprietaire · 10/11 21:03"])
    fake = types.SimpleNamespace(read=lambda q: {"content": content})
    monkeypatch.setitem(sys.modules, "walter_memory.views", fake)
    import walter_memory
    monkeypatch.setattr(walter_memory, "views", fake, raising=False)
    b = retrieval.board(plan("L2", thread="subject:mine"), at=at)
    assert b.sources == ["subject:mine", "subject:a1", "subject:a4"]
    p = plan("L2", thread="subject:x")
    p.horizons = ["instant"]                                                  # right now: 6 h only
    assert retrieval.board(p, at=at).sources == ["subject:a1"]


def test_stale_subject_view_shows_its_age_and_the_horizon_bounds_freshness(monkeypatch):
    from datetime import datetime, timedelta, timezone
    at = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
    asked = []
    fake = types.SimpleNamespace(read=lambda q: (asked.append(q), {"key": q["key"], "depth": "overview", "content": "carte",
                                                                   "stale": True, "built_at": at - timedelta(hours=5)})[1])
    import walter_memory
    monkeypatch.setattr(walter_memory, "views", fake, raising=False)
    monkeypatch.setitem(sys.modules, "walter_memory.views", fake)
    p = plan("L2", thread="subject:abc")
    p.horizons = ["instant"]
    b = retrieval.subject(p, at=at)
    assert asked[0]["max_age_s"] == retrieval.PACK["horizon_max_age_s"]["instant"]
    assert "construite il y a 5 h" in b.text and "peut être périmé" in b.text
    asked.clear()
    retrieval.subject(plan("L2", thread="subject:abc"), at=at)
    assert "max_age_s" not in asked[0]


def test_tasks_and_experience_blocks_from_the_memory_routes():
    from datetime import datetime, timedelta, timezone
    at = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
    seen = []

    def fetch(path, body):
        seen.append((path, body))
        if path == "/v1/tasks/list" and body.get("thread_id"):
            return {"tasks": [{"task_id": "t1", "goal": "Migrer la base", "status": "open", "thread_id": "subject:abc",
                               "updated_at": (at - timedelta(hours=2)).isoformat(), "progress": "2/3 étapes",
                               "attempts": 2, "last_outcome": {"status": "failed", "summary": "timeout"}},
                              {"task_id": "t0", "goal": "Vieux", "status": "done"}]}
        if path == "/v1/tasks/list":
            return {"tasks": [{"task_id": "t1", "goal": "Migrer la base", "status": "open", "thread_id": "subject:abc"},
                              {"task_id": "t2", "goal": "Écrire le guide", "status": "open", "thread_id": "subject:z",
                               "updated_at": (at - timedelta(days=3)).isoformat()},
                              {"task_id": "t3", "goal": "Trier les photos", "status": "suspended", "thread_id": "task:t3",
                               "updated_at": (at - timedelta(hours=5)).isoformat()}]}
        return {"items": [{"at": (at - timedelta(days=1)).isoformat(), "run_id": "r1", "status": "failed",
                           "summary": "Redémarrage du service", "errors": ["port déjà pris"], "lessons": ["arrêter l'ancien"],
                           "solutions": [], "pending": ["relancer"]}]}
    b = retrieval.tasks(plan("L1"), fetch=fetch, at=at)
    assert "[open] Migrer la base" in b.text and "progrès : 2/3 étapes" in b.text and "il y a 2 h" in b.text
    assert "id t1" in b.text                                     # what task_update needs
    assert "Vieux" not in b.text and "Écrire le guide (3 j)" in b.text
    assert "Trier les photos (suspendu, 5 h)" in b.text          # an interrupted task stays visible
    assert b.tokens <= retrieval.PACK["tasks_tokens"] and b.sources == ["t1", "t2", "t3"]
    e = retrieval.experience(plan("L1"), "on relance", fetch=fetch, at=at)       # L1: shown, a recent failure
    assert e.text.splitlines()[1].startswith("- Déjà tenté le 10/11 : Redémarrage du service — échec : port déjà pris")
    assert "Leçon : arrêter l'ancien" in e.text and "Reste : relancer" in e.text
    assert seen[-1][1]["query"] == "on relance" and seen[-1][1]["thread_id"] == "subject:abc"
    old = lambda path, body: {"items": [{"at": (at - timedelta(days=30)).isoformat(), "status": "failed", "summary": "x"}]}
    assert retrieval.experience(plan("L1"), "m", fetch=old, at=at) is None                # old failure, L1: nothing
    assert retrieval.experience(plan("L2"), "m", fetch=old, at=at) is not None
    assert retrieval.tasks(plan("L1"), fetch=lambda p, b: {"tasks": []}, at=at) is None
    light = retrieval.tasks(plan("L0"), fetch=fetch, at=at)       # the lightest context: the thread's own task only
    assert "[open] Migrer la base" in light.text and "Autres objectifs" not in light.text and light.sources == ["t1"]


def test_the_lightest_context_still_carries_the_task_and_a_recent_failure(sources, monkeypatch):
    """12/11: a one-line operation judged L0 was retried blind in a new conversation — its failure was in Memory."""
    monkeypatch.setattr(retrieval, "tasks", lambda p: retrieval.Block("tasks", 3, "Objectifs de ce fil : …"))
    monkeypatch.setattr(retrieval, "experience", lambda p, m: retrieval.Block("experience", 4, "Expérience : déjà tenté…"))
    blocks, notes = retrieval.gather(plan("L0"), "lis le fichier")
    assert [b.id for b in blocks] == ["capabilities", "now", "tasks", "experience"] and not notes
    p = pack(plan("L0"), blocks)
    assert "Expérience" in p.text() and "Objectifs de ce fil" in p.text()


def test_absent_memory_routes_drop_the_block_with_a_note(sources, monkeypatch):
    def absent(*a):
        raise retrieval.RouteAbsent("/v1/tasks/list 404")
    monkeypatch.setattr(retrieval, "tasks", absent)
    monkeypatch.setattr(retrieval, "experience", absent)
    blocks, notes = retrieval.gather(plan("L2"), "et la suite ?")
    assert "tasks: route absent" in notes and "experience: route absent" in notes
    assert not {"tasks", "experience"} & {b.id for b in blocks}


def test_memory_assembly_is_asked_without_tasks_and_experience(sources, monkeypatch):
    budgets = []
    import walter_memory
    fake = types.SimpleNamespace(get_context=lambda m, budget, include_profile, **kw: (budgets.append(budget), {"text": ""})[1])
    monkeypatch.setattr(walter_memory, "context", fake, raising=False)
    monkeypatch.setitem(sys.modules, "walter_memory.context", fake)
    retrieval.gather(plan("L3", caps=("tools", "memory")), "qui décide ?")
    assert budgets and all(b["tasks"] == 0 and b["experience"] == 0 for b in budgets)
