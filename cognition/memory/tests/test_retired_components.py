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
