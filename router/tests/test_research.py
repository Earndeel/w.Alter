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
                 ("3d", "aa_eval", "aa_3d"), ("vision", "aa_eval", "mmmu_pro"), ("engineering", "aa_eval", "idx_engineering"),
                 ("finance", "aa_eval", "idx_finance"), ("strategy", "aa_eval", "idx_strategy_ops"),
                 ("cybersecurity", "aa_eval", "cyber"), ("medical", "aa_eval", "idx_medical"), ("legal", "aa_eval", "idx_legal")]:
        assert need in boards


def test_domain_index_rows_carry_cost_per_task():
    doc = {"evals": {}, "data": [], "indexes": {"idx_engineering": [
        {"slug": "m-1", "name": "M 1 (max)", "index": 60.4, "cost_per_task": 5.46, "time_per_task_s": 1208.0, "sub_scores": {}}]}}
    (r,) = parse_benchmarks("aa_eval", doc)
    assert r["task"] == "idx_engineering" and r["score"] == 60.4 and r["cost"] == 5.46 and r["cost_unit"] == "usd_per_aa_task"


def test_best_hosts_follow_reliability_precision_and_tier():
    """2026-10-22: cheapest usable host = reliable (>= 95 % / 24 h), not below the vendor's own precision; flex only for
    background work."""
    from walter_router.store import db
    with db.connect() as conn:
        conn.execute("insert into models.snapshots (kind, fetched_at, source_url, sha256, row_count, raw) values "
                     "('or_endpoints', now() + interval '1 day', 't', 'test-endpoints', 0, '{}')")
        sid = conn.execute("select snapshot_id from models.snapshots where sha256 = 'test-endpoints'").fetchone()["snapshot_id"]
        rows = [("v/m", "Vendor", "v", "fp4", None, 3.0, 15.0, 100), ("v/m", "Cheap4", "cheap/fp4", "fp4", None, 0.2, 1.0, 100),
                ("x/m", "Vendor", "x", "bf16", None, 2.0, 10.0, 100), ("x/m", "Cheap4", "c/fp4", "fp4", None, 0.2, 1.0, 100),
                ("x/m", "Flaky", "flaky", "bf16", None, 0.5, 2.0, 70), ("x/m", "Flex", "x/flex", "bf16", "flex", 1.0, 5.0, 100)]
        for gm, host, tag, q, tier, pin, pout, up in rows:
            conn.execute("""insert into models.endpoints (snapshot_id, gateway, model_id, gateway_model, host, tag, quantization,
                            service_tier, price_in_1m, price_out_1m, uptime_1d) values (%s,'openrouter',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (sid, "test-" + gm[0], gm, host, tag, q, tier, pin, pout, up))
        best = {(r["model_id"], r["usage"]): r["tag"] for r in conn.execute(
            "select * from models.best_endpoints where model_id like 'test-%'")}
        conn.rollback()
    assert best[("test-v", "interactive")] == "cheap/fp4"      # the vendor itself serves fp4: native precision
    assert best[("test-x", "interactive")] == "x"              # fp4 below bf16 refused, flaky host refused, flex not interactive
    assert best[("test-x", "background")] == "x/flex"


def test_research_categories_cover_every_source_and_part():
    """2026-10-22: every source and every part of a shared source belongs to a category, so `research all` = everything."""
    from walter_router.research import categories, sources
    from walter_router.research.benchmarks import aa_media, arena, design_arena
    parts, plans = categories.plan(list(categories.NAMES))
    assert set(parts) == set(sources.SOURCES) and plans
    assert parts["arena"] is not None and parts["arena"] == set(arena.ARENA_BOARDS.values())
    assert parts["mm"] == set(aa_media.MODULES)
    assert parts["da"] == set(design_arena.CATEGORIES) | {"agents"}


def test_partial_read_merges_into_the_last_snapshot():
    from walter_router.research import sources
    old = {"boards": {"text": {"rows": [1]}, "text_to_image": {"rows": [1]}}, "errors": {"text_to_image": "x"}}
    new = {"boards": {"text_to_image": {"rows": [2]}}, "errors": {}}
    merged = sources.merge("arena", old, new)
    assert merged["boards"]["text"] == {"rows": [1]} and merged["boards"]["text_to_image"] == {"rows": [2]}
    assert merged["errors"] == {}
    da = sources.merge("da", {"categories": {"logo": [1], "agents/fullstack": [1]}}, {"categories": {"logo": [2]}, "registry": {"a": 1}})
    assert da["categories"]["logo"] == [2] and da["agent_categories"] == {"fullstack": [1]} and da["registry"] == {"a": 1}


def test_routes_carry_cost_price_quota_and_host_order(monkeypatch):
    """2026-10-22: a subscription route is priced at its cost price and goes after the paid routes once its weekly
    quota is nearly spent; an OpenRouter route carries the host order the gateway imposes."""
    from walter_router.serve import execution
    from walter_router.store import db
    with db.connect() as conn:
        monkeypatch.setattr(execution, "subscription_costs", lambda c: {"codex": {"plan": "P", "ratio_pace": 0.02,
                                                                                    "used_percent": 10.0}})
        rs = execution.routes(conn, "gpt-6-1-sol", "medium")
        sub = next(r for r in rs if r["access"] == "subscription")
        assert rs[0] is sub and sub["cost_price_1m"]["in"] > 0 and sub["subscription"]["cost_ratio"] == 0.02
        orr = next((r for r in rs if r["hermes_provider"] == "openrouter"), None)
        if orr and orr.get("or_provider"):
            assert orr["or_provider"]["allow_fallbacks"] and orr["or_provider"]["order"][0] == orr["host"]["tag"]
        monkeypatch.setattr(execution, "subscription_costs", lambda c: {"codex": {"plan": "P", "ratio_pace": 0.02,
                                                                                    "used_percent": 95.0}})
        rs = execution.routes(conn, "gpt-6-1-sol", "medium")
        assert rs[0]["access"] != "subscription"
