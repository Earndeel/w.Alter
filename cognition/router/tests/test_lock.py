"""Padlock of the active models (owner, 2026-11-16): locked = the change waits for the owner's Telegram answer (default);
unlocked = the router adopts by itself the model overtaking it, and only informs the owner."""
import json

import pytest

from walter_router.analysis import alerts, telegram
from walter_router.serve import choose
from walter_router.store import db


@pytest.fixture
def conn():
    with db.connect() as c:
        if c.execute("select to_regclass('models.latest_run') as t").fetchone()["t"] is None:
            pytest.skip("schema not migrated")
        if choose.latest_run(c) is None:
            pytest.skip("no refresh yet")
        yield c
        c.rollback()  # the real database is left untouched


def _weak_3d(conn):
    """3d pinned to a weaker model: better ones become 'baseline' challengers (seen by this cycle)."""
    out = choose.set_preference(conn, "3d", pin="claude-opus-5")
    assert out["baseline_challengers"] > 0


def test_a_model_is_locked_by_default_and_a_locked_one_never_switches(conn):
    # the owner opens padlocks himself on the page (16/11: two open): the default is what is checked, not the live set
    assert conn.execute("""select column_default from information_schema.columns where table_schema = 'models'
                           and table_name = 'preferences' and column_name = 'locked'""").fetchone()["column_default"] == "true"
    conn.execute("update models.preferences set locked = true where task = '3d'")
    _weak_3d(conn)
    assert all(c["task"] != "3d" for c in alerts.auto_adopt(conn))
    assert choose.pick(conn, "3d")["model_id"] == "claude-opus-5"


def test_opening_the_padlock_follows_the_best_challenger_and_closes_its_proposals(conn):
    _weak_3d(conn)
    best = max(conn.execute("""select subject, evidence from models.alerts where kind = 'challenger' and task = '3d'
                               and role = 'default' and status = 'baseline' and evidence ? 'boards'""").fetchall(),
               key=lambda a: a["evidence"]["composite"]["challenger"])["subject"]
    out = alerts.set_lock(conn, "3d", None, False)
    assert out["locked"] is False and [c["to"] for c in out["changed"]] == [best]
    assert out["changed"][0]["from"] == "claude-opus-5"
    assert choose.pick(conn, "3d")["model_id"] == best
    assert not conn.execute("""select 1 from models.alerts where kind = 'challenger' and task = '3d'
                               and status in ('open', 'notified')""").fetchone()
    # closed again: stays on the adopted model, nothing more switches
    assert alerts.set_lock(conn, "3d", None, True) == {"task": "3d", "role": "default", "locked": True, "changed": []}
    assert conn.execute("select locked from models.preferences where task = '3d' and role = 'default'").fetchone()["locked"]


def test_a_stale_challenger_is_not_followed(conn):
    _weak_3d(conn)
    conn.execute("update models.alerts set last_seen = now() - interval '5 days' where kind = 'challenger' and task = '3d'")
    assert alerts.set_lock(conn, "3d", None, False)["changed"] == []
    assert choose.pick(conn, "3d")["model_id"] == "claude-opus-5"


def test_opening_an_undeclared_task_pins_the_model_in_use(conn):
    task = conn.execute("""select t.task from models.tasks t where t.interface <> 'tool' and not exists
                           (select 1 from models.preferences p where p.task = t.task) order by t.task limit 1""").fetchone()
    if not task:
        pytest.skip("every task is declared")
    before = choose.pick(conn, task["task"])["model_id"]
    out = alerts.set_lock(conn, task["task"], None, False)
    row = conn.execute("select * from models.preferences where task = %s and role = 'default'", (task["task"],)).fetchone()
    assert row["locked"] is False and row["watch"] == "quality"
    assert row["pinned_model_id"] in [before] + [c["to"] for c in out["changed"]]


def test_closing_an_undeclared_task_changes_nothing(conn):
    task = conn.execute("""select t.task from models.tasks t where t.interface <> 'tool' and not exists
                           (select 1 from models.preferences p where p.task = t.task) order by t.task limit 1""").fetchone()
    if not task:
        pytest.skip("every task is declared")
    assert alerts.set_lock(conn, task["task"], None, True)["changed"] == []
    assert not conn.execute("select 1 from models.preferences where task = %s", (task["task"],)).fetchone()


def test_an_open_tier_follows_the_methods_proposal(conn, monkeypatch):
    seen = []
    monkeypatch.setattr(alerts, "verdict", lambda c, alert_id, decision, note=None, role=None, _resolved=False, by="owner":
                        seen.append((alert_id, decision)) or {})
    conn.execute("delete from models.alerts where kind = 'tier' and role = 'L2'")
    a = conn.execute("""insert into models.alerts (kind, task, role, subject, evidence, status)
                        values ('tier', 'general', 'L2', 'test-model/high', %s::jsonb, 'baseline') returning alert_id""",
                     (json.dumps({"level": "L2"}),)).fetchone()["alert_id"]
    out = alerts.set_lock(conn, "general", "L2", False)
    assert seen == [(a, "adopted")] and out["changed"][0]["to"] == "test-model/high"


def test_unknown_task_is_refused(conn):
    with pytest.raises(KeyError):
        alerts.set_lock(conn, "no-such-task", None, False)


def test_information_message_has_no_buttons_and_names_both_models(conn, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram, "send_with_buttons", lambda text, rows: sent.append((text, rows)))
    out = telegram.notify_auto(conn, [{"task": "3d", "role": "default", "label": "3D", "from": "claude-opus-5",
                                       "to": "claude-opus-5-5"}])
    assert out == {"sent": 1} and sent[0][1] == []
    assert "3D" in sent[0][0] and "→" in sent[0][0] and "cadenas" in sent[0][0]
    assert telegram.notify_auto(conn, []) == {"sent": 0}
