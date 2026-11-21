"""Tests never touch the production database (2026-11-02).

Every test runs against the throwaway database of tests/testdb.sh (WALTER_MEMORY_TEST_DATABASE_URL, default
127.0.0.1:5440). The production DSN is refused outright. When the test database is down, the tests that need a
database are skipped (the pure ones still run): start it with `tests/testdb.sh up`.
"""
import os
import re

import pytest

TEST_DSN = os.environ.get("WALTER_MEMORY_TEST_DATABASE_URL",
                          "postgresql://walter:walter-test-only@127.0.0.1:5440/walter")
if re.search(r"[:@/]5433\b", TEST_DSN) or "walter-pg" in TEST_DSN or "hindsight-pg" in TEST_DSN:
    raise pytest.UsageError("tests refuse the production database (port 5433): use tests/testdb.sh")
os.environ["WALTER_MEMORY_DATABASE_URL"] = TEST_DSN   # read by walter_memory.db at import, before any test module
# purges run by tests write their ledger here, never into the instance's purge ledger
import tempfile  # noqa: E402
os.environ["WALTER_MEMORY_PURGE_LEDGER"] = os.path.join(tempfile.mkdtemp(prefix="walter-purge-ledger-"), "ledger.jsonl")

_NEEDS_DB = re.compile(r"\b(connection\(\)|connect\(\)|record_events?\(|bus\.emit\(|\.drain)")


def _db_up() -> bool:
    try:
        import psycopg
        with psycopg.connect(TEST_DSN, connect_timeout=2) as c:
            c.execute("select 1 from core.schema_migrations limit 1")
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if _db_up():
        return
    skip = pytest.mark.skip(reason="test database down: tests/testdb.sh up")
    seen: dict[str, bool] = {}
    for item in items:
        path = str(item.fspath)
        if path not in seen:
            try:
                seen[path] = bool(_NEEDS_DB.search(open(path, encoding="utf-8").read()))
            except OSError:
                seen[path] = False
        if seen[path]:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _strict_privacy_by_default(request, monkeypatch):
    """The privacy mechanisms are tested under the strict rule (cloud readers see cloud_allowed only, redacted_cloud is
    pseudonymised); the owner's current choice (2026-11-03: everything may be read by the cloud models, no
    pseudonymisation, full Kardex for reasoning) is tested explicitly with the `owner_privacy` marker."""
    from walter_memory import organic
    cur = organic.settings()
    mode = ({"cloud_context": "local_only", "pseudonymise": False, "kardex_cloud": "full"}
            if request.node.get_closest_marker("owner_privacy")
            else {"cloud_context": "cloud_allowed", "pseudonymise": True, "kardex_cloud": "policy"})
    # the owner's pause of the extraction chain (2026-11-14) is a production state: the mechanisms are tested active
    monkeypatch.setattr(organic, "settings", lambda: {**cur, "privacy": mode, "extraction": {"mode": "active"},
                                                     "stages": {}})


def pytest_configure(config):
    config.addinivalue_line("markers", "owner_privacy: run under the owner's current privacy choice (organic.toml)")
    config.addinivalue_line("markers", "real_reconcile: reconciliation asks llm.decide (the test scripts it)")


@pytest.fixture(autouse=True)
def _scripted_reconciliation(request, monkeypatch):
    """Lot 1 (2026-11-19): reconciliation verdicts come from Walter Decision. Without network, the scripted extraction
    model's own references (same_as / supersedes / contradicts) stand in for the decision; a test marked
    `real_reconcile` goes through knowledge.judge and scripts llm.decide itself."""
    from walter_memory import knowledge
    if request.node.get_closest_marker("real_reconcile"):
        return
    # the test database keeps earlier runs' items: a search across threads would find them (same fixture texts)
    monkeypatch.setattr(knowledge, "SEARCH", False)
    from walter_memory import extract2
    monkeypatch.setattr(extract2, "KNOWN_SIMILAR", 0)
    monkeypatch.setattr(knowledge, "judge", lambda batch, **kw: {
        sid: ((st["hint"][0], st["hint_id"], 0.9) if st.get("hint") and st["hint"][0] else ("new", None, None))
        for sid, st, cands in batch})


@pytest.fixture(autouse=True)
def _no_decision_carried_over():
    """Recorded model decisions (processing.decisions) belong to one test: the same fixture text in another test or a
    previous run must not turn a model call into a reuse (2026-11-03)."""
    try:
        import psycopg
        with psycopg.connect(TEST_DSN, connect_timeout=2, autocommit=True) as c:
            c.execute("delete from processing.decisions")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _provider_gate_open(monkeypatch):
    """No real provider limit holds a test's poste unless the test records one (the live hold is never read)."""
    from walter_memory import quota
    monkeypatch.setattr(quota, "gate", lambda *a, **k: {"ok": True})
