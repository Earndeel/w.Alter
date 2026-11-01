"""2026-11-01 reorganisation: the reserve is findable and self-restoring; identical workflows are never rewritten."""
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace

from walter_skills import domains, registry, reserve, retrieval, store


def _skill(root, rel, name, desc="Use when testing.", meta=None):
    d = root / rel / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nBody of {name}\n")
    if meta:
        store.write_sidecar(d, meta)
    return d


def _repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".git").mkdir(exist_ok=True)
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(registry, "ledger", lambda *a, **kw: None)
    monkeypatch.setattr(reserve, "_refresh_async", lambda: None)


def test_reading_a_reserve_skill_restores_it_to_its_domain(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    _skill(tmp_path, "archive", "irs-form-filling",
           meta={"reserve": True, "domain": "productivity", "archived_reason": "dormant", "origin": "hermes-agent"})
    text = retrieval.read_skill("irs-form-filling")
    assert "active again" in text and "Body of irs-form-filling" in text
    assert (tmp_path / "skills/productivity/irs-form-filling/SKILL.md").exists()
    assert not (tmp_path / "archive/irs-form-filling").exists()
    meta = store.read_sidecar(tmp_path / "skills/productivity/irs-form-filling")
    assert meta["origin"] == "hermes-agent" and "reserve" not in meta and "restored_at" in meta
    assert "restore irs-form-filling" in store.git("log", "-1", "--format=%s")


def test_peek_and_merged_skills_are_not_restored(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    _skill(tmp_path, "skills/cloudflare", "cloudflare-pages-deploy")
    _skill(tmp_path, "archive", "cloudflare-pages-deployment-patterns",
           meta={"absorbed_into": "cloudflare-pages-deploy", "domain": "cloudflare"})
    _skill(tmp_path, "archive", "notion", meta={"reserve": True, "domain": "productivity"})
    text = retrieval.read_skill("cloudflare-pages-deployment-patterns")
    assert "merged into `cloudflare-pages-deploy`" in text
    assert (tmp_path / "archive/cloudflare-pages-deployment-patterns").exists()
    retrieval.read_skill("notion", restore=False)
    assert (tmp_path / "archive/notion").exists()


def test_index_lists_entries_first_and_the_reserve_last(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)
    states = {}
    monkeypatch.setattr(domains.registry, "set_state", lambda k, v: states.__setitem__(k, v))
    monkeypatch.setattr(domains.registry, "get_state", lambda k, default=None: states.get(k, default))
    monkeypatch.setattr(domains.registry, "cards", lambda: {})
    _skill(tmp_path, "skills/images", "kie-image-generation-operations")
    _skill(tmp_path, "skills/images", "image-generation", meta={"kind": "entry"})
    _skill(tmp_path, "archive", "face-grid-overlay", meta={"reserve": True, "domain": "images"})
    _skill(tmp_path, "archive", "kie-qwen-image-ops", meta={"absorbed_into": "kie-image-generation-operations", "domain": "images"})
    domains.build()
    page = domains.index("images")
    assert [e["name"] for e in page["entries"]] == ["image-generation", "kie-image-generation-operations", "face-grid-overlay"]
    assert page["entries"][-1]["kind"] == "reserve"
    assert "images : 2 / 0 · réserve 1" in domains.render("skills_search")


def test_curator_never_rewrites_a_workflow_that_already_exists(tmp_path, monkeypatch):
    from walter_skills.curation import operators, signals
    monkeypatch.setattr(store, "ROOT", tmp_path)
    for n in ("a", "b", "c"):
        _skill(tmp_path, "skills/video", n)
    _skill(tmp_path, "archive", "old-chain", meta={"kind": "workflow", "requires": ["c", "a", "b"]})
    active = list(store.iter_skills(root=tmp_path))
    monkeypatch.setattr(signals, "workflow_chains", lambda *a: [{"steps": ["a", "b", "c"], "sessions": 9, "lift": 9.0},
                                                                {"steps": ["b", "c"], "sessions": 9, "lift": 9.0}])
    import numpy as np
    ctx = SimpleNamespace(root=tmp_path, cfg={"workflow_max_step_cosine": 0.75},
                          sig={"active": active, "sim": np.zeros((3, 3))}, aliases={n: n for n in "abc"})
    props = operators.Workflow().propose(ctx)
    assert [p["steps"] for p in props] == [["b", "c"]]


def test_search_answers_a_merged_name_with_its_hub_and_flags_the_reserve():
    meta = {"old": {"absorbed_into": "hub"}, "old2": {"absorbed_into": "hub"}, "notion": {"reserve": True},
            "gone": {"absorbed_into": "archived-hub"}}
    ranked = [("old", 3.0), ("notion", 2.5), ("old2", 2.4), ("gone", 2.2), ("hub", 2.0), ("tv-power", 1.0)]
    out = retrieval.fold(ranked, meta, {"hub", "tv-power"}, k=3)
    assert out == [("hub", 3.0, "active", "old"), ("notion", 2.5, "reserve", None), ("tv-power", 1.0, "active", None)]
