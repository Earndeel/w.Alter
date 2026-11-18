"""`walter engine kernel` (lot E1) once DSH is uninstalled (2026-11-18): no kernel installed is not a drift."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_platform import engine  # noqa: E402


def test_no_kernel_installed_is_reported_as_such_and_never_as_a_drift(tmp_path):
    out = engine.kernel(install=str(tmp_path / "absent"), home=str(tmp_path / "absent" / "home"))
    assert out["installed"] is False and out["ok"] is True and "missing" not in out


def test_a_partial_installation_is_still_verified(tmp_path):
    (tmp_path / "dsh" / "home").mkdir(parents=True)          # a home left without its packages: a drift, not « absent »
    out = engine.kernel(install=str(tmp_path / "dsh"), home=str(tmp_path / "dsh" / "home"))
    assert out["installed"] is True and out["ok"] is False
