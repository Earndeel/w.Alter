"""Drafts go live without a model judge (2026-10-26): only the target is checked, the door keeps its own refusals."""
import subprocess

import pytest

from walter_skills import door, store
from walter_skills.curation import base, operators

SKILL = """---
name: {name}
description: "Use when testing the walter-skills drafts operator with a well formed skill."
---

# Test

1. Run `walter-skills health`.
{extra}"""


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "skills" / "devops" / "existing-skill").mkdir(parents=True)
    (tmp_path / "skills" / "devops" / "existing-skill" / "SKILL.md").write_text(SKILL.format(name="existing-skill", extra=""))
    for k, v in {"ROOT": tmp_path, "SKILLS": tmp_path / "skills", "ARCHIVE": tmp_path / "archive",
                 "DRAFTS": tmp_path / "drafts"}.items():
        monkeypatch.setattr(store, k, v)
    monkeypatch.setattr(base, "review", lambda *a, **k: pytest.fail("the model judge must not be called"))
    return tmp_path


def apply_all(root):
    ctx = base.Context(root=root, mode="shadow", day="2026-10-26", cfg={}, use_models=False)
    op = operators.Drafts()
    return [op.apply(ctx, p) for p in op.propose(ctx)]


def test_patch_and_new_go_live_without_models(tmp_store):
    door.patch("existing-skill", "fix: add a step, evidence from a real run",
               skill_md=SKILL.format(name="existing-skill", extra="2. Then `walter-skills quick`.\n"))
    door.propose("brand-new-skill", SKILL.format(name="brand-new-skill", extra=""), "a reason long enough to pass")
    res = apply_all(tmp_store)
    assert [r["status"] for r in res] == ["done", "done"]
    assert "walter-skills quick" in (tmp_store / "skills/devops/existing-skill/SKILL.md").read_text()
    assert list(tmp_store.glob("skills/*/brand-new-skill/SKILL.md"))
    assert not list((tmp_store / "drafts").glob("*/SKILL.md"))


def test_only_the_target_is_checked(tmp_store):
    door.propose("existing-skill-2", SKILL.format(name="existing-skill-2", extra=""), "a reason long enough to pass")
    (tmp_store / "skills/devops/existing-skill-2").mkdir()
    (tmp_store / "skills/devops/existing-skill-2/SKILL.md").write_text(SKILL.format(name="existing-skill-2", extra=""))
    assert [r["status"] for r in apply_all(tmp_store)] == ["rejected"]


def test_door_still_refuses_secrets(tmp_store):
    with pytest.raises(door.Refused):
        door.patch("existing-skill", "fix: add the key, long enough reason",
                   skill_md=SKILL.format(name="existing-skill", extra="key: sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD\n"))
