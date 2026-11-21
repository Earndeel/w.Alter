"""Preflight bench (2026-11-14): the owner decides first, blind; proposals are anonymous; the report alone names models."""
import json

import pytest

from walter_router.eval import preflight_bench as bench
from walter_router.eval import preflight_bench_web as web

MODS = [{"module": "memory", "line": "La mémoire"}, {"module": "router", "line": "Le bon modèle"}]
Q = {"handling": {"type": "choice"}, "act": {"type": "choice"}, "thread": {"type": "choice"},
     "plan": {"type": "choice"}, "extensive": {"type": "noul"}, "model_level": {"type": "choice"},
     "domain": {"type": "choice"}, "horizon": {"type": "choice"}, "doc_memory": {"type": "noul"},
     "doc_router": {"type": "noul"}, "work": {"type": "noul"}}
LETTERS = dict(zip("ABCD", bench.MODELS))
CASES = [{"id": "f01", "category": "1_simple", "source": "fictif", "letters": LETTERS, "modules": MODS,
          "state": {}, "questions": Q, "fast_path": None,
          "case": {"message": "Quelle heure à Tokyo ?", "candidates": [{"id": "s_x", "title": "Voyage"}],
                   "origin": {"channel": "chat"}, "note": "pas de mémoire utile"}}]
# what each model's single call reads as (model 0 = like the owner, model 1 = oversizes C and L, adds a doc)
READ = {"handling": "answer", "act": "new", "thread": "new", "C": "C0", "L": "L1", "domain": "none",
        "horizon": "none", "docs": [], "work": "no", "confidence": {"plan": 0.9, "model_level": 0.8}}
REF = {"handling": "answer", "act": "new", "thread": "new", "C": "C0", "L": "L1", "docs": [], "work": "no"}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "home", lambda: tmp_path)
    (tmp_path / "cases.json").write_text(json.dumps({"cases": CASES}))
    reads = {f"f01|{bench.MODELS[0]}|1": READ,
             f"f01|{bench.MODELS[1]}|1": {**READ, "C": "C3", "L": "L3", "docs": ["router"]},
             f"f01|{bench.MODELS[2]}|1": {**READ, "act": "continue"}}
    (tmp_path / "readings.json").write_text(json.dumps(reads))
    return tmp_path


def _answer_all(no=0):
    for k, v in REF.items():
        bench.set_reference(no, k, v)


def test_proposals_come_only_after_a_complete_reference_which_then_freezes(home):
    bench.set_reference(0, "C", "C0")
    with pytest.raises(ValueError):
        bench.reveal(0)                                   # reference incomplete
    _answer_all()
    assert "domain" not in bench.required(CASES[0], REF)  # memory fields only when C3/C4
    shown = bench.reveal(0)
    assert [p["letter"] for p in shown["proposals"]] == list("ABCD")
    with pytest.raises(bench.Frozen):
        bench.set_reference(0, "L", "L2")
    out = bench.review(0, {"what": "revise", "key": "L", "value": "L2"})
    assert out["reference"]["L"] == "L1" and out["revised"]["L"] == "L2"   # the blind one is kept


def test_the_page_never_shows_a_model_name_before_or_after_the_reveal(home):
    names = [m.split("/")[0] for m in bench.MODELS] + list(bench.MODELS)
    before = json.dumps(web.cases_view(), ensure_ascii=False)
    _answer_all()
    bench.reveal(0)
    after = json.dumps(web.cases_view(), ensure_ascii=False)
    for text in (before, after, web.PAGE):
        assert not any(n in text for n in names)
    assert "pas de mémoire utile" not in before and "pas de mémoire utile" in after   # case note after the reveal


def test_equal_fields_are_pre_graded_and_the_owner_can_regrade(home):
    _answer_all()
    shown = bench.reveal(0)
    a = next(p for p in shown["proposals"] if p["letter"] == "A")["fields"]
    b = next(p for p in shown["proposals"] if p["letter"] == "B")["fields"]
    assert a["C"]["grade"] == "correct" and b["C"]["grade"] is None and b["docs"]["value"] == ["router"]
    out = bench.review(0, {"what": "grade", "letter": "B", "key": "docs", "grade": "acceptable"})
    assert next(p for p in out["proposals"] if p["letter"] == "B")["fields"]["docs"]["grade"] == "acceptable"
    with pytest.raises(ValueError):
        bench.review(0, {"what": "grade", "letter": "Z", "key": "C", "grade": "correct"})
    assert next(p for p in out["proposals"] if p["letter"] == "D").get("missing")


def test_report_scores_against_the_blind_reference_and_counts_oversizing(home, monkeypatch):
    monkeypatch.setattr(bench, "_daily_volume", lambda: 100)
    _answer_all()
    bench.reveal(0)
    bench.review(0, {"what": "grave", "letter": "B", "value": True})
    bench.review(0, {"what": "preferred", "value": "A"})
    (home / "answers.jsonl").write_text("\n".join(json.dumps(
        {"case": "f01", "model": m, "sample": 1, "ok": True, "ms": 300 + i, "cost_usd": 0.00001}) for i, m in
        enumerate(bench.MODELS[:3])) + "\n")
    rep = bench.report()
    good, big, act = (rep["models"][m]["single_call"] for m in bench.MODELS[:3])
    assert good["overall_strict"] == 1.0 and good["preferred"] == 1 and good["grave_errors"] == 0
    assert big["fields"]["C"]["over"] == 1 and big["fields"]["L"]["over"] == 1 and big["grave_errors"] == 1
    assert big["docs"]["precision"] == 0.0
    assert act["fields"]["act"]["strict"] == 0.0
    assert rep["models"][bench.MODELS[0]]["usd_per_month_1_call"] == pytest.approx(0.03)


def test_build_refuses_to_overwrite_a_bench_already_run(home):
    (home / "answers.jsonl").write_text("{}\n")
    with pytest.raises(RuntimeError):
        bench.build()
