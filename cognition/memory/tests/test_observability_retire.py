"""Cleanup phase 2 (2026-11-09): the copies of agent execution in core.events are proven against walter_logs, event by
event, and removed by a traced, idempotent Memory operation that keeps every real gap and emits no bus event.
Synthetic data only, in the throwaway test database."""
import json
import uuid
from datetime import datetime, timezone

from walter_memory import events, observability as O, purge
from walter_memory.db import connect

AT = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
RUN = uuid.uuid4().hex[:10]
B = uuid.uuid4().int % 10 ** 9 * 10 ** 3      # state.db message numbers unique to this run


def _event(conn, etype, source, source_id, payload, thread):
    eid = str(uuid.uuid4())
    conn.execute("""insert into core.event_keys (source, source_id, event_type, event_id, occurred_at)
                    values (%s, %s, %s, %s, %s)""", (source, source_id, etype, eid, AT))
    conn.execute("""insert into core.events (event_id, event_type, source, source_id, occurred_at, thread_id, payload)
                    values (%s, %s, %s, %s, %s, %s, %s)""", (eid, etype, source, source_id, AT, thread, json.dumps(payload)))
    return eid


def _log(conn, runtime, native, rows):
    sid = f"{runtime}/pytest/{native}"
    conn.execute("insert into walter_logs.sessions (session_id, runtime, native_id) values (%s, %s, %s)",
                 (sid, runtime, native))
    for seq, (typ, call, tool, text, ref) in enumerate(rows, 1):
        conn.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, call_id, tool, text, chars,
                            privacy_class, source_ref, event_key) values (%s,%s,%s,%s,%s,%s,%s,%s,'cloud_allowed',%s,%s)""",
                     (sid, seq, typ, AT, call, tool, text, len(text or ""), ref, f"k{RUN}{seq}{native}"))


def _fixture():
    """Hermes: one exact call, its re-persisted twin (absent from walter_logs), the skill use and its twin, one real
    gap (args differ). Claude Code: one exact call, one with a different output size, one real gap."""
    global RUN, B
    RUN, B = uuid.uuid4().hex[:10], uuid.uuid4().int % 10 ** 9 * 10 ** 3
    h, c = f"h{RUN}", f"c{RUN}"
    raw = json.dumps({"name": "walter-skills"})
    out = '{"ok": true}'
    ids = {}
    with connect() as conn:
        events._ensure_partitions(conn, {AT.replace(day=1, hour=0)})
        _log(conn, "hermes", h, [("tool/call", "call1", "skill_view", raw, "m1c"), ("tool/result", "call1", "skill_view", out, f"m{B + 101}"),
                                 ("tool/call", "call2", "terminal", '{"cmd": "ls"}', "m2c"), ("tool/result", "call2", "terminal", out, f"m{B + 102}")])
        base = {"tool": "skill_view", "args_summary": O.hermes_args(raw), "status": "ok", "output_chars": len(out),
                "session_id": h, "call_id": "call1", "automated": False}
        ids["h_exact"] = _event(conn, "tool.called", "hermes", f"tool:{RUN}101",
                                {**base, "output_ref": f"state.db:messages:{B + 101}"}, h)
        ids["h_twin"] = _event(conn, "tool.called", "hermes", f"tool:{RUN}901",
                               {**base, "output_ref": f"state.db:messages:{B + 901}"}, h)
        sk = {"skill": "walter-skills", "session_id": h, "action": "skill_view"}
        ids["s_exact"] = _event(conn, "skill.used", "hermes", f"skill:{B + 101}", sk, h)
        ids["s_twin"] = _event(conn, "skill.used", "hermes", f"skill:{B + 901}", sk, h)
        ids["h_gap"] = _event(conn, "tool.called", "hermes", f"tool:{RUN}102",
                              {"tool": "terminal", "args_summary": "cmd=\"rm\"", "status": "ok", "output_chars": len(out),
                               "output_ref": f"state.db:messages:{B + 102}", "session_id": h, "call_id": "call2"}, h)
        _log(conn, "claude_code", c, [("tool/call", "t1", "Bash", '{"command": "ls"}', "c1"), ("tool/result", "t1", None, "abc", "c2"),
                                      ("tool/call", "t2", "Read", '{"file": "x"}', "c3"), ("tool/result", "t2", None, "abcdef", "c4"),
                                      ("tool/call", "t3", "Bash", '{"command": "pwd"}', "c5"), ("tool/result", "t3", None, "x", "c6")])
        cb = {"session_id": c, "status": "ok"}
        ids["c_exact"] = _event(conn, "tool.called", "claude_code", f"tool:{RUN}:t1",
                                {**cb, "tool": "Bash", "args_summary": O.agent_args('{"command": "ls"}'), "output_chars": 3,
                                 "call_id": "t1"}, c)
        ids["c_size"] = _event(conn, "tool.called", "claude_code", f"tool:{RUN}:t2",
                               {**cb, "tool": "Read", "args_summary": O.agent_args('{"file": "x"}'), "output_chars": 99,
                                "call_id": "t2"}, c)
        ids["c_gap"] = _event(conn, "tool.called", "claude_code", f"tool:{RUN}:t3",
                              {**cb, "tool": "Bash", "args_summary": "something else", "output_chars": 1, "call_id": "t3"}, c)
    return ids


def _classes(ids):
    with connect() as conn:
        got = {str(e): cls for e, _, _, cls in O.classify(conn)}
        conn.rollback()
    return {k: got.get(v) for k, v in ids.items()}


def test_proof_retire_idempotent_and_silent():
    ids = _fixture()
    cls = _classes(ids)
    assert cls == {"h_exact": O.EXACT, "h_twin": O.CORE_TWIN, "s_exact": O.EXACT, "s_twin": O.CORE_TWIN,
                   "h_gap": "differs: args", "c_exact": O.EXACT, "c_size": O.SIZE_ONLY, "c_gap": "differs: args"}
    dry = O.retire(requested_by="pytest", reason="pytest")
    assert dry["status"] == "dry_run" and not dry["executed"]
    refused = O.retire(requested_by="pytest", reason="pytest", execute=True, expect_sha="0" * 64)
    assert refused["status"].startswith("refused")
    with connect() as conn:
        bus0 = conn.execute("select count(*) n from bus.events").fetchone()["n"]
    done = O.retire(requested_by="pytest", reason="pytest", execute=True, expect_sha=dry["removable_ids_sha256"])
    assert done["status"] == "executed" and done["counts"]["events"] == dry["removable"]
    with connect() as conn:
        left = {str(r["event_id"]) for r in conn.execute("select event_id from core.events where event_id = any(%s::uuid[])",
                                                          (list(ids.values()),))}
        keys = conn.execute("select count(*) n from core.event_keys where event_id = any(%s::uuid[])",
                            (list(ids.values()),)).fetchone()["n"]
        assert conn.execute("select count(*) n from bus.events").fetchone()["n"] == bus0       # no parasitic event
        row = conn.execute("select selector, counts from system.purges where purge_id = %s", (done["purge_id"],)).fetchone()
        assert conn.execute("select count(*) n from system.purge_ledger where kind = 'operation' and target = %s",
                            (O.OPERATION,)).fetchone()["n"] == 1
    assert left == {ids["h_gap"], ids["c_gap"]} and keys == 2       # real gaps stay, with their keys
    assert row["selector"]["operation"] == O.OPERATION and "content" not in json.dumps(row["counts"])
    again = O.retire(requested_by="pytest", reason="pytest", execute=True)
    assert again["status"] == "nothing to remove" and again["removable"] == 0
    assert purge.verify()["present_again"].get("observability_events", 0) == 0


def test_retire_refuses_unless_every_event_has_one_verdict(monkeypatch):
    ids = _fixture()
    real = O.classify
    monkeypatch.setattr(O, "classify", lambda conn: (r for i, r in enumerate(real(conn)) if i))   # one event lost
    r = O.retire(requested_by="pytest", reason="pytest", execute=True)
    assert r["status"].startswith("refused") and not r["executed"]
    with connect() as conn:
        assert conn.execute("select count(*) n from core.events where event_id = any(%s::uuid[])",
                            (list(ids.values()),)).fetchone()["n"] == len(ids)
        conn.execute("set local walter.purge = 'on'")      # leave the test database as the retirement left it
        conn.execute("delete from core.event_keys where event_id = any(%s::uuid[])", (list(ids.values()),))
        conn.execute("delete from core.events where event_id = any(%s::uuid[])", (list(ids.values()),))
