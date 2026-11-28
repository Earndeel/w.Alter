"""Curation without a model judge (2026-10-26): scripted checks decide; the full remarks still reach git."""
import subprocess

import pytest

from walter_skills import postes, store
from walter_skills.curation import base
from walter_skills.curation.operators import issues_body

SKILL = """---
name: big-skill
description: "Use when testing a curation split without any model judge."
---

# Big

1. Run `walter-skills health`.
2. Then `walter-skills quick`.
"""


def test_commit_body_lists_every_remark_in_full():
    long = "MINOR: " + "x" * 400
    body = issues_body({"issues": ["BLOCKING: a", long]})
    assert "- BLOCKING: a" in body and long in body
    assert issues_body({"issues": []}) == ""


@pytest.fixture
def target(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    d = tmp_path / "skills" / "devops" / "big-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL)
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(postes, "ask_json", lambda *a, **k: pytest.fail("no model may judge a curation change"))
    ctx = base.Context(root=tmp_path, mode="shadow", day="2026-10-26", cfg={}, use_models=True)
    s = next(store.iter_skills(root=tmp_path))
    return ctx, s


def test_lossless_split_is_accepted_without_a_judge(target):
    ctx, s = target
    res = {"skill_md": SKILL.split("2.")[0] + "See references/more.md.\n",
           "references": {"references/more.md": "2. Then `walter-skills quick`.\n"}}
    v = base.validate(ctx, "split", [s], s, res)
    assert v["accepted"] and "judge" not in v


def test_lossy_split_is_still_refused(target):
    ctx, s = target
    v = base.validate(ctx, "split", [s], s, {"skill_md": SKILL.split("2.")[0]})
    assert not v["accepted"] and v["reason"] == "lossless"
    assert any("walter-skills quick" in m for m in v["lossless"]["missing"])
