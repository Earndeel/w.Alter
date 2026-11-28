"""Hindsight and the ephemeral sweeper were retired on 2026-10-19 (DECISIONS.md): nothing may bring them back."""
from pathlib import Path

import pytest

from walter_memory import cli

ROOT = Path(__file__).resolve().parents[1]


def test_cli_no_longer_pushes_into_hindsight(capsys):
    with pytest.raises(SystemExit) as exit_:
        cli.main(["hindsight-push"])
    assert exit_.value.code == 2
    assert "hindsight-push" not in capsys.readouterr().err.split("choose from", 1)[-1]


def test_hindsight_adapter_is_gone():
    assert not (ROOT / "walter_memory" / "hindsight_adapter.py").exists()


def test_shipped_units_do_not_run_retired_components():
    for unit in (ROOT / "systemd").iterdir():
        text = unit.read_text()
        assert "hindsight" not in text.lower(), unit.name
        assert "--kind ephemeral" not in text, unit.name
    assert not (ROOT / "systemd" / "ephemeral-sweeper.service").exists()


# Cleanup phase 1 (2026-11-09): the Hindsight tables of `public`, `walter_voice`, `walter_audit`, the Hindsight sync
# mechanics of `legacy` and `kardex.hindsight_sync_state` were dropped. No code may read or write them again
# (migrations are history and stay as they were).
DROPPED = ("public.memory_units", "public.documents", "walter_voice.", "walter_audit.", "memory_outbox",
           "units_sync_state", "hindsight_sync_state", "public.entities", "memory_units_bm25")


def test_no_code_reads_dropped_hindsight_objects():
    offenders = []
    for folder in ("walter_memory", "connectors", "ops", "guardian"):
        for f in (ROOT / folder).rglob("*"):
            if f.is_file() and f.suffix in ("", ".py", ".sh", ".sql") and "__pycache__" not in f.parts:
                text = f.read_text(errors="ignore")
                offenders += [f"{f.relative_to(ROOT)}: {d}" for d in DROPPED if d in text]
    assert not offenders, offenders


def test_purge_has_no_hindsight_option(capsys):
    with pytest.raises(SystemExit):
        cli.main(["purge", "--reason", "x", "--by", "test", "--hindsight"])
    assert "unrecognized arguments: --hindsight" in capsys.readouterr().err
