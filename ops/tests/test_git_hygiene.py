"""Repository hygiene uses real disposable Git repos, without inspecting file contents."""
import os
import subprocess
import time

import pytest

from walter_backup import core


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout

    git("init", "-q")
    (repo / "source.py").write_text("initial\n")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "initial")
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path / "instance"))
    monkeypatch.setattr(core, "repos", lambda cfg=None: [repo])
    monkeypatch.setattr(core, "status", lambda: {
        "conformity": {"ok": True}, "backup_health": {},
        "restorability": {"disk": {"drill_possible_now": True}}})
    return repo, git


def old_file(repo, name):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture\n")
    stamp = time.time() - 72 * 3600
    os.utime(path, (stamp, stamp))
    return path


def test_tracked_bytecode_is_reported_even_in_clean_repo(repository):
    repo, git = repository
    old_file(repo, "package/__pycache__/core.cpython-312.pyc")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "bytecode fixture")
    assert core.repo_state(repo)["dirty"] == 0
    warnings = [item for item in core.check() if item["kind"] == "tracked_generated_files"]
    assert len(warnings) == 1 and warnings[0]["severity"] == "warning"
    assert warnings[0]["evidence"]["tracked_generated_files"] == ["package/__pycache__/core.cpython-312.pyc"]


def test_old_untracked_work_is_reported_without_tracked_changes(repository):
    repo, _ = repository
    name = "work/ébauche précise.py"
    old_file(repo, name)
    state = core.repo_state(repo)
    assert state["dirty"] == 0 and state["untracked"] == 1
    warnings = [item for item in core.check() if item["kind"] == "untracked_work"]
    assert len(warnings) == 1 and warnings[0]["severity"] == "warning"
    assert warnings[0]["evidence"]["untracked_work_files"] == [name]


def test_archives_and_reports_remain_visible_without_being_hygiene_incidents(repository):
    repo, git = repository
    for name in ("archives/proof.txt", "reports/qualification.json", "outputs/analysis.md", "docs/reports/evidence.md"):
        old_file(repo, name)
    old_file(repo, "archives/original/__pycache__/old.pyc")
    git("add", "archives/original/__pycache__/old.pyc")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "preserved evidence fixture")
    state = core.repo_state(repo)
    assert state["untracked"] == 4 and state["untracked_preserved"] == 4
    assert not [item for item in core.check() if item["kind"] in {"untracked_work", "tracked_generated_files"}]


def test_fresh_untracked_work_and_gitignored_caches_do_not_warn(repository):
    repo, _ = repository
    (repo / ".gitignore").write_text("__pycache__/\n")
    old_file(repo, "package/__pycache__/ignored.pyc")
    (repo / "new.py").write_text("fresh\n")
    assert not [item for item in core.check() if item["kind"] in {"untracked_work", "tracked_generated_files"}]


def test_old_untracked_does_not_age_a_fresh_tracked_edit(repository):
    repo, _ = repository
    (repo / "source.py").write_text("fresh edit\n")
    old_file(repo, "work/old.py")
    incidents = core.check()
    assert any(item["kind"] == "untracked_work" for item in incidents)
    assert not any(item["kind"] == "uncommitted_work" for item in incidents)


def test_untracked_names_with_newlines_are_not_split_or_quoted(repository):
    repo, _ = repository
    name = 'work/line\nbreak "quoted".py'
    old_file(repo, name)
    state = core.repo_state(repo)
    assert state["untracked_work_files"] == [name]
    assert state["oldest_untracked_work_age_h"] >= 71


def test_gitignore_does_not_hide_already_tracked_caches(repository):
    repo, git = repository
    old_file(repo, "package/__pycache__/already-tracked.pyc")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tracked fixture")
    (repo / ".gitignore").write_text("__pycache__/\n")
    assert any(item["kind"] == "tracked_generated_files" for item in core.check())


def test_preservation_is_configurable_and_does_not_ignore_other_work(repository, monkeypatch):
    repo, _ = repository
    old_file(repo, "evidence/qualification.json")
    old_file(repo, "work/candidate.py")
    original_config = core.config
    cfg = original_config()
    cfg["git"]["preserved_paths"].append("evidence/**")
    monkeypatch.setattr(core, "config", lambda: cfg)
    state = core.repo_state(repo)
    assert state["untracked"] == 2 and state["untracked_preserved"] == 1
    assert state["untracked_work_files"] == ["work/candidate.py"]


def test_rename_destination_with_spaces_is_aged_as_one_file(repository):
    repo, git = repository
    git("mv", "source.py", "renamed -> source.py")
    stamp = time.time() - 72 * 3600
    os.utime(repo / "renamed -> source.py", (stamp, stamp))
    state = core.repo_state(repo)
    assert state["dirty"] == 1 and state["oldest_tracked_change_age_h"] >= 71


def test_unavailable_git_inventory_does_not_claim_clean(repository, monkeypatch):
    _, _ = repository
    original_sh = core.sh

    def fail_status(*command, **kwargs):
        if "--porcelain=v1" in command:
            return subprocess.CompletedProcess(command, 1, "", "fixture failure")
        return original_sh(*command, **kwargs)

    monkeypatch.setattr(core, "sh", fail_status)
    warnings = [item for item in core.check() if item["kind"] == "git_inspection_failed"]
    assert len(warnings) == 1 and warnings[0]["evidence"]["operations"] == ["status"]
