"""18/11 evening (bench « préflight natif », root causes, not the bench's examples):
- level: a new subject with no recent exchange has no thread to read — the plan's thread options then say memory,
  when the model's domain answer agrees (void_thread_memory);
- dates: periods and durations are kept and said (observations, dates_line);
- pack: a module's M1 brief comes once (tool_cards), the capabilities block is M0 only.
"""
from walter_context import retrieval
from walter_context.plan import ContextPlan, ThreadChoice
from walter_context.preflight import Exchange as Previous, Request, observations, void_thread_memory


def _a(plan, domain):
    return {"plan": {"probabilities": plan}, "domain": {"probabilities": domain}}


NEW = ThreadChoice(id=None, new=True)
SPREAD = {"none": 0.35, "last_exchange": 0.15, "thread": 0.31, "thread_and_memory": 0.18}


def _req(previous_age=None):
    prev = Previous(message="", answer="ok", age_s=previous_age) if previous_age is not None else None
    return Request(turn_id="t", message="m", previous=prev)


def test_a_new_subject_with_no_thread_reads_memory_when_the_domain_agrees():
    assert void_thread_memory(_a(SPREAD, {"projects": 0.65, "none": 0.35}), NEW, _req()) == "void_thread"


def test_no_memory_when_the_model_says_nothing_beyond_the_message_or_no_stored_knowledge():
    assert void_thread_memory(_a({"none": 0.96, "thread": 0.04}, {"projects": 0.9, "none": 0.1}), NEW, _req()) is None
    assert void_thread_memory(_a(SPREAD, {"profile": 0.3, "none": 0.7}), NEW, _req()) is None


def test_a_thread_to_read_keeps_the_plan_as_the_model_said():
    assert void_thread_memory(_a(SPREAD, {"projects": 0.9, "none": 0.1}), ThreadChoice(id="th-1"), _req()) is None
    assert void_thread_memory(_a(SPREAD, {"projects": 0.9, "none": 0.1}), NEW, _req(previous_age=60)) is None


def test_periods_and_durations_are_observations():
    sig = {"context.dates": {"spans": [
        {"text": "cette semaine", "date": "2026-11-16", "end": "2026-11-22", "found": 0.96},
        {"text": "3 jours", "duration": "P3D", "found": 0.8},
        {"text": "14h", "time": "14:00", "found": 0.9}]}}
    got = observations(sig, "a-t-elle changé cette semaine, sur 3 jours, à 14h ?")["dates"]
    assert [d["text"] for d in got] == ["cette semaine", "3 jours"]          # « 14h » alone still names no day
    assert got[0]["end"] == "2026-11-22" and got[1]["duration"] == "P3D"


def _plan(*dates):
    return ContextPlan(turn_id="t", thread=NEW, act="new", level="L1", observations={"dates": list(dates)}).validate()


def test_the_dates_line_says_periods_lengths_and_both_readings():
    line = retrieval.dates_line(_plan(
        {"text": "ce week-end", "date": "2026-11-21", "end": "2026-11-22", "past": "2026-11-14",
         "past_end": "2026-11-15", "ambiguous": True},
        {"text": "ces derniers jours", "date": "2026-11-12", "end": "2026-11-19", "approx": True},
        {"text": "3 jours", "duration": "P3D"}))
    assert "« ce week-end » = du samedi 21 novembre 2026 au dimanche 22 novembre 2026" in line
    assert "(ou du samedi 14 novembre 2026 au dimanche 15 novembre 2026 si c'est le passé)" in line
    assert "« ces derniers jours » = du jeudi 12 novembre 2026 au jeudi 19 novembre 2026 (bornes approximatives)" in line
    assert "« 3 jours » = une durée de 3 jours, pas une date" in line


def test_a_module_brief_comes_once(monkeypatch):
    notes = [{"id": "memory.m0", "module": "memory", "content": "M0 mem"},
             {"id": "memory.manifest", "module": "memory", "content": "M1 mem"}]
    monkeypatch.setattr(retrieval, "_notes", lambda ttl=600: notes)
    p = ContextPlan(turn_id="t", thread=NEW, act="new", level="L3", capabilities=["tools", "memory"],
                    domains=["projects"])
    text = retrieval.capabilities(p).text + retrieval.tool_cards(p).text
    assert text.count("M1 mem") == 1
    # a domain that reads the owner's memory brings its brief even when the capability is not asked
    q = ContextPlan(turn_id="t", thread=NEW, act="new", level="L1", capabilities=["tools"], domains=["profile"])
    assert retrieval.tool_cards(q).sources == ["memory"]
