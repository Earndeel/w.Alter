"""Walter Engine native (2026-11-17) — offline tests: journal, DSH takeover, client events, web sign-in, identity,
budget, command environment. No network, no model: the live checks are core/scenarios/v1/engine_native.py and
engine_api_e2e.py against a running engine."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_engine import api, config, identity, importer, journal  # noqa: E402


# ── journal ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_journal_seq_survives_a_torn_line_and_a_reload(tmp_path):
    st = journal.Store(tmp_path)
    s = st.create(cwd="/w", sid="a")
    s.append("user/message", {"text": "un", "turn": 1, "source": {"kind": "user"}})
    s.close()
    with open(tmp_path / "a.jsonl", "a") as fh:
        fh.write('{"type": "assistant/mess')               # crash mid-write
    st2 = journal.Store(tmp_path)
    s2 = st2.get("a")
    assert s2.seq == 1
    ev = s2.append("assistant/message", {"text": "deux", "turn": 1})
    s2.close()
    assert ev["seq"] == 2 and [e["seq"] for e in journal.Store(tmp_path).get("a").events] == [1, 2]


def test_surface_pairs_every_tool_call_and_starts_at_the_window(tmp_path):
    s = journal.Store(tmp_path).create(cwd="/w", sid="b")
    s.append("user/message", {"text": "vieux", "source": {"kind": "user"}})                       # 1 (before the cut)
    s.append("assistant/message", {"text": "", "tool_calls": [{"id": "c0", "name": "bash"}]})      # 2
    s.append("tool/result", {"callId": "c0", "content": "x"})                                     # 3
    s.append("user/message", {"text": "récent", "source": {"kind": "user"}})                      # 4
    s.append("assistant/message", {"text": "", "tool_calls": [{"id": "c1", "name": "bash"}, {"id": "c2", "name": "read"}]})
    s.append("tool/result", {"callId": "c2", "content": "lu"})                                    # c1 never answered
    s.append("tool/call", {"callId": "n", "name": "memory_search", "nested": True})
    s.append("tool/result", {"callId": "n", "content": "nested", "nested": True})
    s.append("compaction/window", {"cut_seq": 3, "content": "résumé"})                            # 9: cut at 3
    surf = [m for _, m in journal.surface(s)]
    assert surf[0] == {"role": "user", "content": "résumé"}
    assert [m["role"] for m in surf[1:]] == ["user", "assistant", "tool", "tool"]                 # orphan c0 dropped
    assert [m.get("tool_call_id") for m in surf[3:]] == ["c1", "c2"]
    assert "inconnu" in surf[3]["content"] and surf[4]["content"] == "lu"
    assert all("nested" not in (m.get("content") or "") for m in surf)


def test_an_imported_session_continues_after_the_source_last_seq(tmp_path):
    s = journal.Store(tmp_path).create(cwd="/w", sid="c", seq_base=50,
                                       events=[{"type": "turn/start", "seq": 10, "time": 1, "data": {"turn": 1}}])
    assert s.append("turn/start", {"turn": 2})["seq"] == 51


# ── DSH takeover ──────────────────────────────────────────────────────────────────────────────────────────────────
DSH = [
    {"type": "session", "version": 4, "id": "session-1", "createdAt": 1794540753078, "cwd": "/user/x/workspace",
     "delegationDepth": 0},
    {"type": "turn/start", "seq": 1, "time": 1, "data": {"turn": 1}},
    {"type": "user/message", "seq": 2, "time": 2, "data": {"content": [{"type": "text", "text": "règles"}],
                                                          "source": {"kind": "agent-instructions"}}},
    {"type": "user/message", "seq": 3, "time": 3, "data": {"content": [{"type": "text", "text": "bonjour"}],
                                                          "source": {"kind": "user", "rpcId": "r1"}}},
    {"type": "step/start", "seq": 4, "time": 4, "data": {}},
    {"type": "assistant/message", "seq": 5, "time": 5, "data": {"turn": 1, "step": 1, "message": {"content": [
        {"type": "reasoning", "text": "je réfléchis"}, {"type": "text", "text": "je regarde"},
        {"type": "tool-call", "id": "c1", "name": "bash", "arguments": "{\"command\":\"ls\"}"}]}}},
    {"type": "tool/call", "seq": 6, "time": 6, "data": {"callId": "c1", "name": "bash", "arguments": "{\"command\":\"ls\"}",
                                                       "turn": 1, "step": 1}},
    {"type": "tool/result", "seq": 7, "time": 7, "data": {"turn": 1, "step": 1, "message": {"toolCallId": "c1",
                                                         "content": [{"type": "text", "text": "a b"}], "isError": False}}},
    {"type": "turn/end", "seq": 8, "time": 8, "data": {"turn": 1, "reason": {"kind": "completed"}}},
    {"type": "compaction/summary", "seq": 9, "time": 9, "data": {"shadowedRange": {"start": 2, "end": 7}, "summary": "s"}},
    {"type": "user/message", "seq": 10, "time": 10, "data": {"content": [{"type": "text", "text": "point de reprise"}],
                                                            "source": {"kind": "compact-checkpoint"}}},
    {"type": "compaction/end", "seq": 11, "time": 11, "data": {}},
    {"type": "turn/start", "seq": 12, "time": 12, "data": {"turn": 2}},
    {"type": "turn/end", "seq": 13, "time": 13, "data": {"turn": 2, "reason": {"kind": "aborted"}}},
    {"type": "step/end", "seq": 14, "time": 14, "data": {}},
]


def test_a_dsh_journal_becomes_a_native_one_with_the_same_seq_numbers():
    hdr, events, st = importer.convert(DSH)
    by = {e["seq"]: e for e in events}
    assert hdr["seq_base"] == 14 and hdr["cwd"] == "/user/x/workspace" and hdr["depth"] == 0
    assert 2 not in by and 4 not in by and 9 not in by                     # instructions, steps, summary: dropped
    assert by[3]["data"] == {"text": "bonjour", "turn": None, "source": {"kind": "user", "rpcId": "r1"}}
    assert by[5]["data"]["text"] == "je regarde" and by[5]["data"]["reasoning"] == "je réfléchis"
    assert by[5]["data"]["tool_calls"] == [{"id": "c1", "name": "bash", "arguments": "{\"command\":\"ls\"}"}]
    assert by[7]["data"]["name"] == "bash" and by[7]["data"]["content"] == "a b"
    assert by[8]["data"]["status"] == "ok" and by[13]["data"]["status"] == "cancelled"
    assert by[10]["type"] == "compaction/window" and by[10]["data"]["cut_seq"] == 8
    assert by[10]["data"]["content"] == "point de reprise" and st["windows"] == 1


def test_import_is_idempotent_completes_bindings_and_never_touches_dsh(tmp_path):
    zstd = pytest.importorskip("zstandard")
    home = tmp_path / "dsh"
    for sid, cwd in (("session-1", "/ws"), ("session-2", "/ws"), ("session-3", "/tmp/probe")):
        d = home / "sessions" / f"-{cwd.strip('/').replace('/', '-')}-" / sid
        d.mkdir(parents=True)
        lines = [{**DSH[0], "id": sid, "cwd": cwd}, *DSH[1:]]
        (d / "session.v4.jsonl.zstd").write_bytes(zstd.ZstdCompressor().compress(
            ("\n".join(json.dumps(x) for x in lines) + "\n").encode()))
    before = {p: p.read_bytes() for p in home.rglob("*.zstd")}
    bindings = tmp_path / "api" / "bindings.json"
    bindings.parent.mkdir()
    bindings.write_text(json.dumps({"version": 1, "sessions": {"telegram/e2e/x": {
        "session_id": "telegram/e2e/x", "kernel": "session-1", "interface": "telegram", "door": "telegram",
        "principal": {"kind": "owner", "id": "e2e"}}}}))
    out = tmp_path / "sessions"
    r1 = importer.import_sessions(home, out, bindings, workspace="/ws")
    assert r1["imported"] == 2 and r1["new_bindings"] == 1 and not r1["errors"]      # probe workspace not taken
    rows = json.loads(bindings.read_text())["sessions"]
    assert rows["web/owner/session-2"]["principal"] == {"kind": "owner", "id": "owner"}
    head = json.loads((out / "session-1.jsonl").read_text().splitlines()[0])
    assert head["walter_key"] == "dsh/vm/session-1" and head["principal"]["kind"] == "test"   # e2e resolved
    r2 = importer.import_sessions(home, out, bindings, workspace="/ws")
    assert r2["imported"] == 0 and r2["skipped"] == 2
    assert before == {p: p.read_bytes() for p in home.rglob("*.zstd")}


def test_the_web_sign_in_secret_is_taken_over_without_being_shown(tmp_path, capsys):
    pytest.importorskip("yaml")
    home = tmp_path / "dsh"
    home.mkdir()
    secret = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    (home / ".credentials.yaml").write_text(
        f"version: 1\nrecords:\n  client-connection/browser-session:\n    kind: grant\n    payload:\n"
        f"      version: 1\n      secret: {secret}\n")
    assert importer.import_web_secret(home, tmp_path / "state")
    f = tmp_path / "state" / "web" / "cookie.secret"
    assert f.read_text().strip() == secret and oct(f.stat().st_mode & 0o777) == "0o600"
    assert secret not in capsys.readouterr().out


# ── client events ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_client_events_keep_the_contract_vocabulary():
    ev = lambda t, d: {"type": t, "seq": 1, "time": 2, "data": d}                       # noqa: E731
    assert api.to_client_event(ev("turn/end", {"turn": 3, "reason": {"kind": "aborted"}}))["status"] == "cancelled"
    assert api.to_client_event(ev("turn/end", {"turn": 3, "reason": {"kind": "blocked"}}))["status"] == "budget_exhausted"
    notice = ev("user/message", {"text": "fini", "source": {"kind": "subagent-settled"}})
    assert api.to_client_event(notice) is None and api.to_client_event(notice, rich=True)["type"] == "notice"
    nested = ev("tool/call", {"name": "memory_search", "nested": True})
    assert api.to_client_event(nested) is None and api.to_client_event(nested, rich=True)["type"] == "tool.called"
    u = api.to_client_event(ev("user/message", {"text": "x", "source": {"kind": "user", "rpcId": "k"}}))
    assert u == {"seq": 1, "at": 2, "type": "message.user", "request_id": "k", "text": "x"}


# ── web sign-in ───────────────────────────────────────────────────────────────────────────────────────────────────
class Req:
    def __init__(self, host, cookie=None, origin=None):
        self.headers = {k: v for k, v in (("host", host), ("cookie", cookie), ("origin", origin)) if v is not None}


def _settings(tmp_path, **kw):
    return config.Settings(state=tmp_path / "state", trusted_hosts=["portal.example", "100.1.2.3:3080"],
                           login_url_file=tmp_path / "login-url", web_cookie_days=365, **kw)


def test_web_cookies_minted_here_and_by_dsh_both_sign_in(tmp_path):
    from walter_engine.server import WebAuth, _b64
    auth = WebAuth(_settings(tmp_path))
    cookie = auth.mint("portal.example").split(";")[0]
    assert cookie.startswith("walter-auth-") and auth.authenticated(Req("portal.example", cookie))
    assert not auth.authenticated(Req("other.example", cookie))                       # bound to its authority
    now = int(time.time() * 1000)
    body = _b64(json.dumps({"version": 1, "authority": "portal.example", "issuedAt": now,
                            "expiresAt": now + 86_400_000}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(auth.secret, body.encode(), hashlib.sha256).digest())
    dsh = f"{auth.cookie_name('portal.example', 'dsh-auth-')}=v1.{body}.{sig}"
    assert auth.authenticated(Req("portal.example", dsh))
    forged = f"{auth.cookie_name('portal.example', 'dsh-auth-')}=v1.{body}.{_b64(b'x' * 32)}"
    assert not auth.authenticated(Req("portal.example", forged))


def test_the_web_fence_accepts_loopback_and_trusted_hosts_only(tmp_path):
    from walter_engine.server import WebAuth
    auth = WebAuth(_settings(tmp_path))
    assert auth.fenced(Req("127.0.0.1:3080")) and auth.fenced(Req("portal.example"))
    assert auth.fenced(Req("100.1.2.3:3080")) and not auth.fenced(Req("100.1.2.3:9999"))
    assert not auth.fenced(Req("evil.example")) and not auth.fenced(Req("portal.example", origin="https://evil.example"))
    auth.write_login_url()
    url = (tmp_path / "login-url").read_text()
    assert auth.launch in url and oct((tmp_path / "login-url").stat().st_mode & 0o777) == "0o600"


# ── identity, policy door ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_test_account_is_a_test_principal_on_every_door(monkeypatch):
    monkeypatch.setattr(identity, "registry", lambda: {"owner": ["owner", "monsieur"], "test": ["e2e"]})
    assert identity.resolve({"kind": "owner", "id": "e2e"}) == {"kind": "test", "id": "e2e", "claimed": "owner"}
    assert identity.channel_of(identity.resolve({"kind": "machine", "id": "e2e"})) == "test"
    with pytest.raises(identity.IdentityError):
        identity.resolve({"kind": "owner", "id": "inconnu"})
    assert identity.acts_as_owner({"kind": "test", "id": "e2e"}, {"kind": "test", "id": "e2e"})
    assert not identity.acts_as_owner({"kind": "test", "id": "e2e"}, {"kind": "owner", "id": "owner"})


def test_a_test_conversation_is_judged_under_the_test_preset(tmp_path):
    from walter_engine.policy import IFACE
    sys.path.insert(0, str(config.CORE_ROOT / "security"))
    from walter_security import policy as wp
    p = wp.load(wp.POLICY)
    decide = lambda iface: wp.decide(p, tool="mcp__walter__browser_session", args={}, interface=iface,  # noqa: E731
                                     depth=0, home="/root")["decision"]
    assert IFACE["test"] == "test" and decide(IFACE["telegram"]) == "allow" and decide(IFACE["test"]) == "ask"


# ── engine helpers (no network) ───────────────────────────────────────────────────────────────────────────────────
BUDGET = {"max_steps": 80, "max_turn_min": 45, "grace_steps": 3, "grace_min": 5,
          "levels": {"L1": {"checkpoint": 8, "max_steps": 20, "max_turn_min": 10},
                     "L2": {"checkpoint": 14, "max_steps": 36, "max_turn_min": 20}}}


@pytest.fixture
def engine(tmp_path):
    from walter_engine import engine as E
    eng = E.Engine(_settings(tmp_path, budget=BUDGET))
    yield eng
    asyncio.run(eng.doors.close())
    asyncio.run(eng.llm.close())


def test_budget_ceilings_follow_the_stated_effort(engine):
    from walter_engine.engine import at_least
    c = engine._ceilings({"effort": "L2"})
    assert (c["checkpoint"], c["max_steps"], c["max_ms"]) == (14, 36, 20 * 60_000)
    assert engine._ceilings({"effort": "L2", "channel": "machine"})["max_steps"] == 80   # machine: general ceilings
    assert engine._verdict(c, 13, 0) == "go" and engine._verdict(c, 14, 0) == "checkpoint"
    assert engine._verdict(c, 36, 0) == "conclude" and engine._verdict(c, 39, 0) == "stop"
    assert at_least("L1", "L2") == "L2" and at_least("L3", "L2") == "L3" and at_least("L1", None) == "L1"


def test_commands_never_see_the_engine_credentials_and_carry_the_run(engine, monkeypatch):
    monkeypatch.setenv("WALTER_LLM_TOKEN", "tok")
    monkeypatch.setenv("WALTER_MEMORY_GATEWAY_TOKEN", "tok2")
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "test", "id": "e2e"})
    a.run_id = "run-1"
    child = engine.spawn_child(a, description="d", model=None, effort=None)
    env = engine.shell_env(child)
    assert "WALTER_LLM_TOKEN" not in env and "WALTER_MEMORY_GATEWAY_TOKEN" not in env
    assert env["WALTER_RUN_ID"] == "run-1" and env["WALTER_DELEGATION_DEPTH"] == "1"
    assert env["WALTER_RUN_CHANNEL"] == "machine" and env["WALTER_SESSION_ID"] == child.key
    assert engine.shell_env(a)["WALTER_RUN_CHANNEL"] == "test"
    assert a.policy_door == "test" and child.policy_door == "test"
    head = json.loads(child.session.path.read_text().splitlines()[0])
    assert head["parent"] == a.sid and head["parent_key"] == a.key and head["depth"] == 1


def test_a_unit_without_login_environment_still_gives_commands_a_home(engine, monkeypatch):
    import pwd
    monkeypatch.delenv("HOME", raising=False)
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    env = engine.shell_env(a)
    assert env["HOME"] == pwd.getpwuid(os.getuid()).pw_dir and env["USER"]
    monkeypatch.setenv("HOME", "/srv/elsewhere")
    assert engine.shell_env(a)["HOME"] == "/srv/elsewhere"          # a real HOME is never overridden


def test_an_output_that_is_not_utf8_is_journaled_visibly_never_lost(tmp_path):
    s = journal.Store(tmp_path).create(cwd="/w", sid="u")
    name = os.fsdecode(b"rapport-\xd0.txt")                  # a file name with a stray byte (surrogate-escaped)
    ev = s.append("tool/result", {"callId": "c1", "content": f"dossier :\n{name}"})
    s.close()
    again = journal.Store(tmp_path).get("u").events
    assert ev["seq"] == 1 and again[0]["data"]["content"].endswith("rapport-\\xd0.txt") and ev["data"] == again[0]["data"]


def test_a_tool_is_never_run_without_its_required_arguments(engine):
    from walter_engine.tools import builtin
    builtin.register(engine.registry)
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    res = asyncio.run(engine.execute_tool(a, "read", {"path": "/etc/hostname"}, via="python", journal_call=True))
    assert res.is_error and "file_path" in res.content and res.meta["invalid_arguments"] == ["file_path"]
    kinds = [(e["type"], e["data"].get("nested")) for e in a.session.events]
    assert kinds[-2:] == [("tool/call", True), ("tool/result", True)]       # the call and its result, both journaled


def test_tool_discovery_reads_french_queries_plurals_and_accents():
    from walter_engine.tools import builtin, Registry
    reg = Registry()
    builtin.register(reg)
    names = lambda q: [r["name"] for r in reg.search(q)]                       # noqa: E731
    assert {"read", "write", "glob"} & set(names("fichiers"))
    assert "read" in names("lire un fichier") and names("Mémoire") is not None
    assert names("read")[0] == "read"                                          # English still first on its name


# ── configuration ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_unreadable_instance_config_is_said_never_silently_dropped(tmp_path, monkeypatch):
    """17/11: two [native] tables made the instance file unreadable; the engine ran on neutral defaults (no trusted
    hosts: the portal answered 403) without a word. Now the error is logged and `check` fails on it."""
    good = tmp_path / "good.toml"
    good.write_text('[native]\ntrusted_hosts = ["portal.example"]\n')
    bad = tmp_path / "bad.toml"
    bad.write_text('[native]\ntrusted_hosts = ["portal.example"]\n[native]\nweb_cookie_days = 365\n')

    class Inst:
        path = good

        def config(self, module, name):
            return str(self.path)

        def root(self):
            return str(tmp_path)

    inst = Inst()
    monkeypatch.setattr(config, "_instance", lambda: inst)
    monkeypatch.setattr(config, "module_root", lambda name: None)
    s = config.load(tmp_path / "state")
    assert s.trusted_hosts == ["portal.example"] and s.config_error is None
    inst.path = bad
    s = config.load(tmp_path / "state")
    assert s.trusted_hosts == [] and "bad.toml" in (s.config_error or "")


def test_a_turn_cut_by_the_engine_stopping_is_resumed_as_its_continuation(engine, tmp_path, monkeypatch):
    """A restart in the middle of a turn: the run is closed `interrupted` (engine_restart — Memory suspends its
    objective), never « cancelled » like an owner's stop, and the resumed turn is its child with the same plan
    (socle_e2e B/E, 17/11: the native engine closed it `cancelled` and resumed it with no parent)."""
    from walter_engine import engine as E
    monkeypatch.setattr(config, "instance_root", lambda: tmp_path / "instance")      # never the real DSH run file
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "test", "id": "e2e"})
    a.session.append("turn/start", {"turn": 1}, sync=True)
    engine._active(a.sid, True)
    plan = {"thread": "task:t1", "act": "continue", "task": "general", "model_level": "L2", "channel": "test"}
    engine._track_run(a, "run-cut", 1, carry={"run_id": "run-cut", "channel": "test", "plan": plan, "open": True})
    rows = json.loads(engine.runs_file.read_text())
    rows[a.key]["pid"] = 2 ** 22 + 12345                                              # the stopped process
    engine.runs_file.write_text(json.dumps(rows))
    a.session.close()
    asyncio.run(engine.doors.close())
    asyncio.run(engine.llm.close())

    again = E.Engine(_settings(tmp_path, budget=BUDGET))
    ended, noticed = [], []

    async def run_end(run_id, key, status, outcome=None):
        ended.append((run_id, key, status, outcome))
    monkeypatch.setattr(again.doors, "run_end", run_end)
    monkeypatch.setattr(again, "notice", lambda ag, text, kind: noticed.append((ag, kind)))
    try:
        asyncio.run(again._recover())
        assert len(ended) == 1 and ended[0][0] == "run-cut" and ended[0][2] == "cancelled"
        assert ended[0][3]["status"] == "interrupted" and ended[0][3]["error"]["kind"] == "engine_restart"
        assert len(noticed) == 1 and noticed[0][1] == "engine-restart"
        b = noticed[0][0]
        assert b.last["run_id"] == "run-cut" and b.last["plan"] == plan and b.last["channel"] == "test"
        assert b.last["open"] is False and json.loads(again.runs_file.read_text()) == {}
    finally:
        asyncio.run(again.doors.close())
        asyncio.run(again.llm.close())
