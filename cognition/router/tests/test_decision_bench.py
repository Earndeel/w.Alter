"""Decision bench (2026-11-13): the owner labels blind on Telegram, the models' answers stay hidden until the report."""
import json

import pytest

from walter_router.eval import decision_bench as bench

CASES = [
    {"id": "c1", "level": "comprehension", "source": "fictif",
     "case": {"message": "Planifie mon voyage", "previous": None,
              "candidates": [{"id": "t1", "title": "Voyage au Japon"}]},
     "state": {"new_message": "Planifie mon voyage"},
     "questions": {"act": {"type": "choice", "criteria": {"new": "", "continue": "", "approve": "", "correct": "", "inform": ""}},
                   "thread": {"type": "choice", "criteria": {"t1": "continues: Voyage", "new": "opens"}},
                   "plan": {"type": "choice", "criteria": {"none": "", "last_exchange": "", "thread": "", "thread_and_memory": ""}},
                   "model_level": {"type": "choice", "criteria": {"L1": "", "L2": "", "L3": ""}},
                   "work": {"type": "noul"}, "extensive": {"type": "noul"}}},
    {"id": "t1", "level": "triage", "source": "fictif",
     "case": {"state": {"network": "whatsapp", "thread_kind": "single", "messages": [
         {"from": "other", "minutes_ago": 1, "text": "Tu m'ouvres ?"}]}},
     "state": {}, "questions": {"action": {"type": "choice", "criteria": {"ignore": "", "remember": "", "notify": "", "prepare_reply": ""}},
                                "urgency": {"type": "choice", "criteria": {"now": "", "today": "", "later": ""}},
                                "needs_reply": {"type": "noul"}}},
]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "home", lambda: tmp_path)
    sent = []
    monkeypatch.setattr(bench, "_send", lambda text, rows: sent.append((text, rows)))
    (tmp_path / "cases.json").write_text(json.dumps({"cases": CASES}))
    return tmp_path, sent


def test_a_case_is_shown_with_its_questions_and_never_a_models_answer(home):
    tmp, sent = home
    (tmp / "answers.jsonl").write_text(json.dumps({"case": "c1", "model": "m", "ok": True,
                                                   "answers": {"act": {"choice": "SECRET-ANSWER"}}}) + "\n")
    assert bench.send_next()["sent"] == "c1"
    text, rows = sent[0]
    assert "Planifie mon voyage" in text and "SECRET-ANSWER" not in text + json.dumps(rows)
    labels = [b["text"] for r in rows for b in r]
    assert "2 · Voyage au Japon" in labels and "2 · Nouveau sujet" in labels and "Passer ce cas" in labels
    assert max(len(b["callback_data"]) for r in rows for b in r) <= 64        # Telegram's limit
    assert all(b["callback_data"].startswith("wr:b:") for r in rows for b in r)  # the door's existing Router prefix


def test_each_press_records_one_answer_and_a_finished_case_brings_the_next(home):
    tmp, sent = home
    qs = bench.labelled_questions(CASES[0])
    for qi, (key, _, opts) in enumerate(qs):
        out = bench.button(f"wr:b:0:{qi}:{'x' if key == 'work' else 0}")
        assert out["ok"]
    labels = json.loads((tmp / "labels.json").read_text())["c1"]
    assert labels["_done"] and labels["act"] == "new" and labels["work"] is None   # « ? » = no gold for it
    assert out["drop"] == ["wr:b:0:"] and sent and "Tu m'ouvres" in sent[-1][0]


def test_skip_and_unknown_buttons(home):
    tmp, _ = home
    assert bench.button("wr:b:1:s")["toast"] == "Cas passé"
    assert json.loads((tmp / "labels.json").read_text())["t1"]["_skipped"]
    assert bench.button("wr:b:99:0:0")["ok"] is False


def test_report_scores_each_model_against_the_owners_answers_only(home):
    tmp, _ = home
    (tmp / "labels.json").write_text(json.dumps({"t1": {"action": "notify", "urgency": "now", "needs_reply": "yes",
                                                        "_done": True}}))
    rows = [{"case": "t1", "model": "good", "ok": True, "ms": 400, "cost_usd": 0.00001, "answers": {
                "action": {"choice": "notify", "confidence": 0.9}, "urgency": {"choice": "now", "confidence": 0.8},
                "needs_reply": {"type": "noul", "noul": 0.9}}},
            {"case": "t1", "model": "bad", "ok": True, "ms": 900, "cost_usd": 0.00002, "answers": {
                "action": {"choice": "ignore", "confidence": 0.95}, "urgency": {"choice": "later", "confidence": 0.7},
                "needs_reply": {"type": "noul", "noul": 0.2}}},
            {"case": "t1", "model": "bad", "ok": False, "ms": 30000, "error": "TimeoutError"}]
    (tmp / "answers.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    r = bench.report()
    tri = r["levels"]["triage"]
    assert tri["action"]["good"]["accuracy"] == 1 and tri["action"]["bad"]["accuracy"] == 0
    assert tri["needs_reply"]["good"]["accuracy"] == 1 and tri["action"]["bad"]["confidence_when_wrong"] == 0.95
    assert r["models"]["bad"]["failures"] == 1 and r["labelled_cases"] == 1


def test_owner_messages_that_look_like_a_secret_or_a_system_text_are_not_drawn():
    assert bench._usable("Tu peux regarder pourquoi le cycle du Router a échoué ?")
    assert not bench._usable("voici la clé sk-abcdefghijklmnopqrstuv")
    assert not bench._usable("<command-name>/clear</command-name>")
    assert not bench._usable("ok")


def test_the_web_page_shows_cases_and_questions_never_a_models_answer_and_shares_the_labels(home):
    from walter_router.eval import decision_bench_web as web
    tmp, sent = home
    (tmp / "answers.jsonl").write_text(json.dumps({"case": "c1", "model": "m", "ok": True,
                                                   "answers": {"act": {"choice": "SECRET-ANSWER"}}}) + "\n")
    view = web.cases_view()
    assert "SECRET-ANSWER" not in json.dumps(view) + web.PAGE
    c1 = view["cases"][0]
    assert "Planifie mon voyage" in c1["context"] and [q["key"] for q in c1["questions"]][:2] == ["act", "thread"]
    for qi in range(len(c1["questions"])):
        out = web.label({"no": 0, "qi": qi, "oi": None if qi == 1 else 0})
    assert out["done"] and out["labels"]["thread"] is None and not sent      # the web page never sends Telegram
    assert web.label({"no": 0, "qi": 0, "oi": 1})["labels"]["act"] == "continue"   # an answer can be changed
    assert web.label({"no": 1, "skip": True})["labels"]["_skipped"]
    assert bench.status()["labelled"] == 1 and bench.status()["skipped"] == 1


def test_the_models_answers_are_shown_only_after_the_owner_answered_and_then_his_answers_freeze(home):
    from walter_router.eval import decision_bench_web as web
    tmp, _ = home
    rows = [{"case": "t1", "model": "m", "ok": True, "ms": 400, "answers": {
                "action": {"choice": "notify", "confidence": 0.9}, "urgency": {"choice": "now", "confidence": 0.8},
                "needs_reply": {"type": "noul", "noul": 0.9}}},
            {"case": "t1", "model": "m", "ok": True, "ms": 500, "answers": {
                "action": {"choice": "ignore", "confidence": 0.6}, "urgency": {"choice": "now", "confidence": 0.7},
                "needs_reply": {"type": "noul", "noul": 0.8}}},
            {"case": "t1", "model": "m", "ok": True, "ms": 450, "answers": {
                "action": {"choice": "notify", "confidence": 0.7}, "urgency": {"choice": "later", "confidence": 0.5},
                "needs_reply": {"type": "noul", "noul": 0.2}}}]
    (tmp / "answers.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ValueError):
        bench.reveal(1)                                            # not answered yet: nothing shown
    for qi, oi in ((0, 2), (1, 0), (2, None)):                     # notify, now, « ? »
        web.label({"no": 1, "qi": qi, "oi": oi})
    m = bench.reveal(1)["models"][0]
    a, u, r = m["questions"]
    assert (a["answer"], a["agree"], a["of"], a["confidence"], a["match"]) == ("notify", 2, 3, 0.8, True)
    assert u["match"] is True and r["answer"] == "yes" and r["match"] is None and a["label"] == "Me prévenir"
    assert web.cases_view()["cases"][1]["revealed"]
    with pytest.raises(bench.RevealedError):
        web.label({"no": 1, "qi": 0, "oi": 0})
    assert bench.button("wr:b:1:0:0")["ok"] is False
    assert json.loads((tmp / "labels.json").read_text())["t1"]["action"] == "notify"
