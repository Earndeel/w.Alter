"""search.rerank_pools (07/11): one rerank call for every context section, each section cut back to its own rows."""
from walter_memory import search


def test_one_call_orders_every_pool(monkeypatch):
    calls = []

    def fake(query, rows, limit, timeout=8):
        calls.append(len(rows))
        return sorted(rows, key=lambda r: -r["s"])
    monkeypatch.setattr(search, "_rerank", fake)
    rec = [{"ref_id": "r1", "text": "a", "s": 1}, {"ref_id": "r2", "text": "b", "s": 5}]
    kno = [{"ref_id": "k1", "text": "c", "s": 3}, {"ref_id": "r2", "text": "b", "s": 5}, {"ref_id": "k2", "text": "d", "s": 9}]
    out = search.rerank_pools("q", {"records": (rec, 1), "knowledge": (kno, 2)})
    assert calls == [4]                                   # the union, once (r2 shared)
    assert [r["ref_id"] for r in out["records"]] == ["r2"]
    assert [r["ref_id"] for r in out["knowledge"]] == ["k2", "r2"]


def test_rerank_is_memoized_and_skipped_when_trivial(monkeypatch):
    import walter_memory.read_policy as rp
    from walter_memory import processing
    monkeypatch.setattr(rp, "query_privacy", lambda q: "cloud_allowed")
    monkeypatch.setattr(rp, "filter_cloud_rows", lambda conn, rows: rows)
    monkeypatch.setattr(search, "connection", lambda: __import__("contextlib").nullcontext(None))
    seen = []
    monkeypatch.setattr(processing, "decide_once", lambda p, v, inputs, call, **k: (seen.append(inputs) or ([1, 0], True)))
    rows = [{"ref_id": "a", "text": "x", "privacy_class": "cloud_allowed"},
            {"ref_id": "b", "text": "y", "privacy_class": "cloud_allowed"}]
    assert [r["ref_id"] for r in search._rerank("q", rows, 2)] == ["b", "a"]
    assert seen and seen[0]["query"] == "q" and len(seen[0]["docs"]) == 2 and "x" not in str(seen[0])
    assert search._rerank("q", rows[:1], 1) == rows[:1] and len(seen) == 1     # one document: nothing to order


def test_rerank_executes_through_the_gateway_door(monkeypatch):
    """SOCLE A6: the order comes from llm.rerank (walter-llm /v1/rerank, the Router's poste), keyed by the poste."""
    import walter_memory.read_policy as rp
    from walter_memory import llm, processing
    monkeypatch.setattr(rp, "query_privacy", lambda q: "cloud_allowed")
    monkeypatch.setattr(rp, "filter_cloud_rows", lambda conn, rows: rows)
    monkeypatch.setattr(search, "connection", lambda: __import__("contextlib").nullcontext(None))
    asked = []
    monkeypatch.setattr(llm, "rerank", lambda q, docs, **kw: asked.append((q, docs, kw)) or {
        "results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}], "model": "m"})
    seen = []
    monkeypatch.setattr(processing, "decide_once", lambda p, v, inputs, call, **k: (seen.append(inputs) or call()))
    rows = [{"ref_id": "a", "text": "x", "privacy_class": "cloud_allowed"},
            {"ref_id": "b", "text": "y", "privacy_class": "cloud_allowed"}]
    assert [r["ref_id"] for r in search._rerank("q", rows, 2)] == ["b", "a"]
    assert asked[0][1] == ["x", "y"] and asked[0][2]["top_n"] == 2 and asked[0][2]["processor"] == "search.rerank"
    assert seen[0]["poste"] == "rerank" and "model" not in seen[0]
