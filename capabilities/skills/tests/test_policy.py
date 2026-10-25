"""The exposure policy: the single place that decides what an agent sees."""
from types import SimpleNamespace

import pytest

from walter_skills import policy


def row(name, score=0.5, kind="", requires=()):
    return {"name": name, "score": score, "state": "active", "summary": f"Use when {name}", "domain": "d",
            "kind": kind, "requires": list(requires)}


class FakeEngine:
    version, calibration, aliases = "test", {}, {}

    def __init__(self, rows, symptoms=()):
        self.rows, self.symptoms = rows, list(symptoms)

    def rank(self, message, context="", session=None, k=15):
        return self.rows[:k]

    def symptom_matches(self, text, k=5):
        return self.symptoms

    def row(self, name, score, state):
        return row(name, score)


@pytest.fixture
def env(monkeypatch):
    real_get = policy.config.get
    monkeypatch.setattr(policy.config, 'get', lambda section: real_get(section) |
                        ({'discovery': 'shortlist'} if section == 'policy' else {}))
    state = {"shown": set(), "n_prev": 0, "session": {}, "journal": []}
    monkeypatch.setattr(policy.registry, "recently_shown", lambda sid, n: (state["shown"], state["n_prev"]))
    monkeypatch.setattr(policy.registry, "journal_retrieval", lambda *a, **k: state["journal"].append(a))
    monkeypatch.setattr(policy.history, "session_history", lambda sid, al: state["session"])
    monkeypatch.setattr(policy.domains, "render", lambda tool: f"MAP({tool})")
    return state


def use(monkeypatch, eng):
    monkeypatch.setattr(policy, "engine", lambda: eng)


def test_machine_prompts_and_short_messages_get_nothing(env, monkeypatch):
    use(monkeypatch, FakeEngine([row(f"s{i}") for i in range(20)]))
    assert policy.expose("message", "<task-notification> agent finished").text == ""
    assert policy.expose("message", "ok merci").text == ""


def test_new_session_gets_up_to_k_max_cards(env, monkeypatch):
    use(monkeypatch, FakeEngine([row(f"s{i}") for i in range(20)]))
    e = policy.expose("message", "le gateway hermes ne répond plus sur telegram", session_id="x", runtime="claude_code")
    assert len(e.shown) == 15 and "skill_read" in e.text


def test_hermes_gets_its_own_tool_names_and_the_map_on_first_turn(env, monkeypatch):
    use(monkeypatch, FakeEngine([row("s1")]))
    e = policy.expose("message", "lis mes derniers messages beeper", runtime="hermes", first_turn=True)
    assert e.text.startswith("MAP(walter_skill_search)") and "walter_skill_read" in e.text


def test_ongoing_session_only_new_cards_and_follow_ups_get_nothing(env, monkeypatch):
    use(monkeypatch, FakeEngine([row(f"s{i}") for i in range(20)]))
    env.update(shown={"s0", "s1"}, n_prev=1)
    e = policy.expose("message", "et pour le token du bot telegram tu as vérifié ?", session_id="x")
    assert "s0" not in e.shown and "s1" not in e.shown and all(int(n[1:]) < 12 for n in e.shown)
    assert policy.expose("message", "ok vas y continue", session_id="x").shown == []


def test_workflow_first_and_replaces_its_sub_skills(env, monkeypatch):
    use(monkeypatch, FakeEngine([row("a"), row("b"), row("wf", kind="workflow", requires=("a", "b")), row("c")]))
    e = policy.expose("message", "génère la vidéo publicitaire avec référence", session_id="x")
    assert e.shown[0] == "wf" and "a" not in e.shown and "b" not in e.shown and "c" in e.shown


def test_confidence_shrinks_the_list_only_when_calibrated(env, monkeypatch):
    eng = FakeEngine([row("s0", 0.99)] + [row(f"s{i}", 0.5) for i in range(1, 20)])
    use(monkeypatch, eng)
    eng.calibration = {"confident_p1": None}
    assert len(policy.expose("message", "une demande assez longue pour passer", session_id="x").shown) == 15
    eng.calibration = {"confident_p1": 0.95}
    assert len(policy.expose("message", "une autre demande assez longue ici", session_id="y").shown) == 8


def test_errors_need_a_marker_and_a_specific_symptom_match(env, monkeypatch):
    use(monkeypatch, FakeEngine([], symptoms=[("beeper-messages", 21.0), ("weak", 4.0)]))
    assert policy.expose("error", "all good, 3 files copied").shown == []
    e = policy.expose("error", "Error: Beeper API returns 404 when using /v0/messages")
    assert e.shown == ["beeper-messages"]


def test_on_demand_mode_has_no_per_message_shortlist_or_ranker(env, monkeypatch):
    original = policy.config.get
    monkeypatch.setattr(policy.config, 'get', lambda section: original(section) |
                        ({'discovery': 'on_demand'} if section == 'policy' else {}))
    def no_engine():
        raise AssertionError('Index navigation must not warm the ranker')
    monkeypatch.setattr(policy, 'engine', no_engine)
    first = policy.expose('message', 'génère une vidéo publicitaire avec référence', first_turn=True)
    assert first.text == 'MAP(skills_search)' and first.shown == []
    later = policy.expose('message', 'lis mes derniers messages beeper', session_id='new-topic')
    assert later.text == '' and later.shown == []
    start = policy.expose('session_start', '')
    assert start.text == 'MAP(skills_search)'
