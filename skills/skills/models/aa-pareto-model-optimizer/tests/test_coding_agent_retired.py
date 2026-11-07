from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh_coding_agent_retired", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_refresh_snapshot_contains_only_the_intelligence_axis(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--output-dir", str(tmp_path), "--quiet"])
    monkeypatch.setattr(
        MODULE,
        "scrape_intelligence",
        lambda anchor: [
            {
                "name": "Model A",
                "slug": "model-a",
                "intelligence_index": 45.0,
                "aa_cost_per_task_intelligence_usd": 0.2,
                "intelligence_source_url": "https://example.invalid/model-a",
                "intelligence_status": "ok",
            }
        ],
    )
    assert not hasattr(MODULE, "scrape_agentic")
    assert not hasattr(MODULE, "parse_coding_agent_rsc")

    args = MODULE.parse_args()
    assert not hasattr(args, "min_agentic")
    payload, _, _ = MODULE.run(args)
    persisted = json.loads((tmp_path / "latest.json").read_text())

    assert set(payload["frontiers"]) == {"intelligence_aa"}
    assert set(persisted["frontiers"]) == {"intelligence_aa"}
    assert not any("agentic" in key or "coding_agent" in key for key in payload["counts"])
    assert not any("agentic" in key for key in payload["sources"])
    assert not any("agentic" in key for row in payload["data"] for key in row)
    assert not (tmp_path / "raw-agentic.json").exists()
