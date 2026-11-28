from __future__ import annotations

import json

from adaptive_operator.shadow_sanitize import sanitize_benchmark_report


def test_sanitized_benchmark_keeps_metrics_and_removes_local_identifiers():
    source = {
        "passed": True,
        "failures": [],
        "scenarios": [{"id": "A", "status": "observed", "source_call_id": "call-secret"}],
        "replay_errors": ["quarantined_invalid_pair:123:call-secret"],
        "live_probe": {"context_path": "/home/owner/private.json", "presence": {"os_version": "15"}},
        "user_presence": {"user_active": None},
        "measurements": {"C": {"run_count": 30}},
        "measurements_global": {"run_count": 180},
        "policy": {"totals": {"L0": 1}},
        "counters": {"clicks": 0},
        "integrity": {"lot20_hash_verified": True},
        "device_context_cache": {"resolutions": 100},
        "measurement_basis": {"token_estimate": "ceil(chars/4)"},
        "evidence_class": "live_context_plus_v1_replay",
        "postcondition_satisfied": "unknown",
        "v1_event_count": 277,
        "replay_quarantine_count": 10,
        "warmup_runs_per_measured_scenario": 10,
        "measured_runs_per_scenario": 30,
    }

    sanitized = sanitize_benchmark_report(source)
    encoded = json.dumps(sanitized)

    assert sanitized["measurements_global"]["run_count"] == 180
    assert sanitized["scenarios"] == [{"id": "A", "status": "observed"}]
    assert sanitized["replay_quarantine_count"] == 10
    assert "call-secret" not in encoded
    assert "/home/owner/" not in encoded
    assert "replay_errors" not in sanitized
    assert "live_probe" not in sanitized
    assert "user_presence" not in sanitized
