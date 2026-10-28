"""Host-side boundary regressions: no Docker daemon or production data is used."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

from walter_lab import sandbox


@pytest.fixture
def docker(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "run" and getattr(run, "produce", None):
            work = Path(argv[argv.index("-v") + 1].rsplit(":", 1)[0])
            run.produce(work)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sandbox.subprocess, "run", run)
    monkeypatch.setattr(sandbox, "_execute", run)
    return run, calls


def test_source_link_rejected_before_docker_without_changing_host_mode(tmp_path, docker):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "private"
    outside.write_text("test-only")
    outside.chmod(0o600)
    (source / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        sandbox.run(str(source), ["true"])
    assert stat.S_IMODE(outside.stat().st_mode) == 0o600
    assert not docker[1]


@pytest.mark.parametrize("kind", ["fifo", "hardlink", "source_root_link"])
def test_nonordinary_sources_rejected(tmp_path, docker, kind):
    source = tmp_path / "source"
    source.mkdir()
    if kind == "fifo":
        os.mkfifo(source / "pipe")
    elif kind == "hardlink":
        outside = tmp_path / "private"
        outside.write_text("test-only")
        os.link(outside, source / "linked")
    else:
        link = tmp_path / "source-link"
        link.symlink_to(source, target_is_directory=True)
        source = link
    with pytest.raises(ValueError):
        sandbox.run(str(source), ["true"])
    assert not docker[1]


@pytest.mark.parametrize("kind", ["symlink", "directory_link", "fifo", "hardlink"])
def test_outputs_rejected_without_exporting_host_data(tmp_path, docker, kind):
    outside = tmp_path / "private"
    outside.write_text("test-only")

    def produce(work):
        if kind == "symlink":
            (work / "out" / "result").symlink_to(outside)
        elif kind == "directory_link":
            (work / "out" / "result").symlink_to(tmp_path, target_is_directory=True)
        elif kind == "fifo":
            os.mkfifo(work / "out" / "result")
        else:
            os.link(outside, work / "out" / "result")

    docker[0].produce = produce
    output = tmp_path / "export"
    with pytest.raises(ValueError):
        sandbox.run(None, ["true"], out_dir=output)
    assert not output.exists()


def test_known_credentials_are_not_mounted(tmp_path, docker):
    source = tmp_path / "source"
    source.mkdir()
    for name in (".env", ".env.production", "credentials.json", "id_ed25519", "safe.py"):
        (source / name).write_text("fixture")
    (source / ".aws").mkdir()
    (source / ".aws" / "config").write_text("fixture")
    seen = []
    docker[0].produce = lambda work: seen.extend(p.name for p in (work / "src").iterdir())
    sandbox.run(str(source), ["true"])
    assert seen == ["safe.py"]


def test_existing_export_is_never_overwritten(tmp_path, docker):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result").write_text("old")
    output = tmp_path / "export"
    output.symlink_to(outside, target_is_directory=True)
    docker[0].produce = lambda work: (work / "out" / "result").write_text("new")
    with pytest.raises((ValueError, FileExistsError)):
        sandbox.run(None, ["true"], out_dir=output)
    assert (outside / "result").read_text() == "old"


def test_source_and_output_copy_limits(tmp_path, docker):
    source = tmp_path / "source"
    source.mkdir()
    (source / "big").write_bytes(b"x" * 9)
    with pytest.raises(ValueError, match="limit"):
        sandbox.run(str(source), ["true"], max_bytes=8)
    assert not docker[1]
    docker[0].produce = lambda work: (work / "out" / "big").write_bytes(b"x" * 9)
    output = tmp_path / "export"
    with pytest.raises(ValueError, match="limit"):
        sandbox.run(None, ["true"], out_dir=output, max_bytes=8)
    assert not output.exists()


def test_regular_tree_keeps_executable_bit_and_exports(tmp_path, docker):
    source = tmp_path / "source"
    source.mkdir()
    executable = source / "run.sh"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)

    def produce(work):
        assert (work / "src" / "run.sh").stat().st_mode & stat.S_IXUSR
        (work / "out" / "nested").mkdir()
        (work / "out" / "nested" / "result").write_text("result")

    docker[0].produce = produce
    output = tmp_path / "export"
    result = sandbox.run(str(source), ["true"], out_dir=output)
    assert result["outputs"] == str(output)
    assert (output / "nested" / "result").read_text() == "result"


def test_probe_fails_on_nonzero_status(monkeypatch):
    import json
    seen = {"uid": 65534, "env_keys": [], "root_home_visible": False, "internet": False,
            "host_browser_api": False, "host_postgres": False, "can_write_root_fs": False}
    monkeypatch.setattr(sandbox, "run", lambda *a, **kw: {"rc": 1, "timed_out": False,
                                                         "stdout_tail": json.dumps(seen), "stderr_tail": "failed"})
    assert sandbox.probe()["ok"] is False


@pytest.mark.parametrize("payload", ["{}", "[]", '{"uid": 65534}', '{"uid": true, "env_keys": []}'])
def test_probe_fails_on_incomplete_or_invalid_evidence(monkeypatch, payload):
    monkeypatch.setattr(sandbox, "run", lambda *a, **kw: {"rc": 0, "timed_out": False,
                                                         "stdout_tail": payload, "stderr_tail": ""})
    assert sandbox.probe()["ok"] is False


def test_entry_replaced_after_lstat_never_reads_link_target(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    candidate = source / "candidate"
    candidate.write_text("safe")
    private = tmp_path / "private"
    private.write_text("test-only")
    destination = tmp_path / "destination"
    destination.mkdir()
    real_open = sandbox.os.open
    replaced = False

    def raced_open(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == "candidate" and not replaced:
            replaced = True
            candidate.unlink()
            candidate.symlink_to(private)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(sandbox.os, "open", raced_open)
    source_fd = sandbox._open_directory(source)
    target_fd = sandbox._open_directory(destination)
    try:
        with pytest.raises(ValueError, match="changed"):
            sandbox._copy_tree(source_fd, target_fd, source=True, max_bytes=100,
                               max_entries=10, max_file_bytes=100)
    finally:
        os.close(source_fd)
        os.close(target_fd)
    assert not list(destination.iterdir())


def test_invalid_output_is_checked_without_export_request(docker):
    docker[0].produce = lambda work: (work / "out" / "link").symlink_to("/missing")
    with pytest.raises(ValueError, match="symlink"):
        sandbox.run(None, ["true"])


def test_timeout_stops_container_before_output_validation(tmp_path, docker, monkeypatch):
    real_run = docker[0]

    def timeout(argv, **kwargs):
        if argv[1] == "run":
            raise subprocess.TimeoutExpired(argv, 1, output=b"last output", stderr=b"last error")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "run", timeout)
    monkeypatch.setattr(sandbox, "_execute", timeout)
    result = sandbox.run(None, ["true"], timeout=1)
    assert result["timed_out"] and result["rc"] == 124
    assert result["stdout_tail"] == "last output" and result["stderr_tail"] == "last error"
    assert docker[1][-1][1:3] == ["rm", "-f"]


def test_entry_limit_includes_excluded_files(tmp_path, docker):
    source = tmp_path / "source"
    source.mkdir()
    for i in range(3):
        (source / f".env.{i}").write_text("fixture")
    with pytest.raises(ValueError, match="limit"):
        sandbox.run(str(source), ["true"], max_entries=2)
    assert not docker[1]


def test_output_streams_are_drained_with_bounded_tails():
    import sys
    result = sandbox._execute([sys.executable, "-c", "import os; os.write(1, b'x' * 200000); os.write(2, b'y' * 200000)"], timeout=5)
    assert result.returncode == 0
    assert result.stdout == b"x" * 4000 and result.stderr == b"y" * 2000
