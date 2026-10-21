"""research/ (2026-10-21): native sources that replaced the aa-pareto skill cache, AA evaluations, AA Music."""
from __future__ import annotations

import json

from walter_router.analysis.parse import parse_benchmarks
from walter_router.research import web
from walter_router.research.benchmarks import aa, aa_evaluations, aa_media


def test_html_tables_reads_cells_like_inner_text():
    page = ("<table><tr><th></th><th>Model</th><th>Elo</th><th>Samples</th></tr>"
            "<tr><td>1</td><td><div>Suno v6</div></td><td>1146<span>±20</span></td><td>2,458</td></tr></table>")
    (table,) = web.html_tables(page)
    assert table[0] == ["", "Model", "Elo", "Samples"]
    assert table[1][1] == "Suno v6" and table[1][2].startswith("1146")


def test_music_board_needs_no_price_column():
    rows = [["", "Range", "Model", "Elo", "Samples"], ["1", "1-2", "Suno v6", "1146±20\n95% interval", "2,458"]]
    spec = aa_media.TASK_SPECS["music_vocals"]
    payload = aa_media.build_task_payload(spec, rows, "2026-10-21T00:00:00+00:00")
    assert payload["rows"][0]["model"] == "Suno v6" and payload["rows"][0]["quality_score"] == 1146.0


def _flight(obj) -> str:
    return '<script>self.__next_f.push([1,' + json.dumps("5:" + json.dumps(obj)) + '])</script>'


def test_aa_evaluations_merge_and_scale():
    page = _flight({"models": [{"slug": "m-1", "shortName": "M 1 (max)", "harveyLab": 0.1305, "aa3dElo": 1190.5},
                               {"slug": "m-2", "shortName": "M 2", "mmmuPro": 0.8}]})
    page += _flight({"currentModel": {"slug": "m-1", "healthbenchProfessional": 0.66}})
    models = aa_evaluations.merge(aa_evaluations._objects(page))
    assert models["m-1"]["harvey_lab"] == 0.1305 and models["m-1"]["healthbench_pro"] == 0.66
    doc = {"evals": {k: {"unit": u} for k, (_, _, u) in aa_evaluations.EVALS.items()}, "data": list(models.values())}
    rows = {(r["task"], r["external_key"]): r for r in parse_benchmarks("aa_eval", doc)}
    assert rows[("harvey_lab", "m-1")]["score"] == 13.05 and rows[("harvey_lab", "m-1")]["score_unit"] == "%"
    assert rows[("aa_3d", "m-1")]["score"] == 1190.5 and rows[("mmmu_pro", "m-2")]["score"] == 80.0


def test_aa_intelligence_records_keep_cost_per_task():
    raw = [{"slug": "x-high", "shortName": "X (high)", "intelligenceIndex": 50.1,
            "intelligenceIndexCostPerTask": {"cost": {"total": 0.12}}}, {"slug": "y", "intelligenceIndex": None}]
    (r,) = aa.records(raw)
    assert r["aa_cost_per_task_intelligence_usd"] == 0.12 and r["intelligence_status"] == "ok"


def test_specialised_tasks_have_their_boards():
    from walter_router.store import db
    with db.connect() as conn:
        boards = {(r["task"], r["benchmark"], r["bench_task"]) for r in conn.execute("select * from models.task_benchmarks")}
    for need in [("medical", "aa_eval", "healthbench_pro"), ("legal", "aa_eval", "harvey_lab"), ("science", "aa_eval", "critpt"),
                 ("long_context", "aa_eval", "lcr"), ("writing", "arena", "text_creative"), ("music", "aa_mm", "music_vocals"),
                 ("3d", "aa_eval", "aa_3d"), ("vision", "aa_eval", "mmmu_pro")]:
        assert need in boards
