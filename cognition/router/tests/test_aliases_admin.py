from __future__ import annotations

import pytest

from walter_router import aliases_admin, db, identity


@pytest.fixture
def conn(tmp_path, monkeypatch):
    f = tmp_path / "aliases_auto.json"
    f.write_text('{"aliases": {}}')
    monkeypatch.setattr(identity, "AUTO_ALIASES", f)
    identity.reload()
    with db.connect() as c:
        yield c
        c.rollback()
    identity.reload()


def _unscored(conn, like):
    return conn.execute("""select model_id from models.catalog where not ranked and model_id like %s limit 1""",
                        (like,)).fetchone()["model_id"]


def test_validated_link_is_applied_and_removable(conn):
    key = _unscored(conn, "riverflow-v2-5%")
    out = aliases_admin.add(conn, key, "riverflow-2-5-pro", "Design Arena riverflow-2.5-pro = OpenRouter riverflow v2.5 pro")
    assert out["added"] == key and identity.normalize("openrouter", f"sourceful/{key}")[0] == "riverflow-2-5-pro"
    aliases_admin.remove(key)
    assert identity.normalize("openrouter", f"sourceful/{key}")[0] == key


@pytest.mark.parametrize("key,target,reason,err", [
    ("gpt-6-1-sol", "gpt-6-astra", "long enough reason text here", "already has its own scores"),
    ("riverflow-v2-5-pro", "glm-5-3", "long enough reason text here", "too different"),
    ("riverflow-v2-5-pro", "riverflow-2-5-pro", "short", "evidence"),
])
def test_bad_links_are_refused(conn, key, target, reason, err):
    with pytest.raises(ValueError, match=err):
        aliases_admin.add(conn, key, target, reason)
