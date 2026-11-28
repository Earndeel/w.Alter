from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh_cli_defaults", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_refresh_defaults_to_intelligence_cutoff_35(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    args = MODULE.parse_args()

    assert args.min_intel == 35.0
    assert args.max_incremental_cost_per_score_point == 0.75
