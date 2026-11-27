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


def test_a_delegation_is_told_to_conclude_before_its_budget_cuts_it(engine):
    """2026-11-20: the Router's advisor was cancelled at budget_seconds (25 min) after 37 tool calls, never told to
    conclude — the general machine ceiling is 45 min. A delegation's own budget is now the conclude deadline."""
    c = engine._ceilings({"effort": "L3", "channel": "machine"}, conclude_ms=880_000)
    assert c["max_ms"] == 880_000
    assert engine._verdict(c, 5, 879_000) == "go" and engine._verdict(c, 5, 880_000) == "conclude"
    assert engine._verdict(c, 5, 3_000_000) == "conclude"          # never a hard stop: the API cancel is the end
    assert engine._ceilings({"effort": "L2"})["max_ms"] == 20 * 60_000   # owner turns unchanged


def test_a_module_agent_is_a_sub_agent_with_the_module_s_identity(engine, tmp_path, monkeypatch):
    """2026-11-21 (owner): the Router's agent is « le Router », a sub-agent of Walter that maintains its module. The
    module declares it (maintenance.json `agent`); Walter's subagent tool gives it that identity and its poste."""
    from walter_engine.tools import Exec, agents
    root = tmp_path / "router"
    (root / "contracts").mkdir(parents=True)
    (root / "guardian").mkdir()
    (root / "contracts" / "maintenance.json").write_text(json.dumps(
        {"agent": {"identity": "guardian/agent.md", "task": "general"}}))
    (root / "guardian" / "agent.md").write_text("# pour les humains\n\n---\n\nTu es **le Router**.")
    monkeypatch.setattr(agents.config, "module_root", lambda name: root if name == "router" else None)
    seen = {}

    async def run_child(child, prompt, cancel=None):
        seen.update(prompt=prompt, model=child.model)
        return {"status": "ok", "text": "vu", "tools": 0}
    monkeypatch.setattr(engine, "run_child", run_child)
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    ex = Exec(engine=engine, agent=a, call_id="c1", name="subagent", cancel=asyncio.Event())
    res = asyncio.run(agents.subagent({"description": "quotas", "prompt": "Regarde les quotas.", "agent": "router"}, ex))
    assert not res.is_error and seen["prompt"].startswith("Tu es **le Router**.")
    assert seen["prompt"].endswith("Regarde les quotas.") and "pour les humains" not in seen["prompt"]
    assert seen["model"] == "general"
    res = asyncio.run(agents.subagent({"description": "x", "prompt": "y", "agent": "memory"}, ex))
    assert res.is_error and "no module agent" in res.content


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
    monkeypatch.setattr(config, "instance_root", lambda: tmp_path / "instance")
    legacy = tmp_path / "instance" / "state" / "core" / "engine" / "intake" / "open-runs.json"   # DSH's run file
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"dsh/vm/old": {"run_id": "run-dsh", "pid": 2 ** 22 + 54321}}))
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
        assert "run-dsh" in legacy.read_text()        # DSH's run file is no longer read (2026-11-18), nor rewritten
    finally:
        asyncio.run(again.doors.close())
        asyncio.run(again.llm.close())


# ── payload trace (lot 0, 2026-11-23) ──
def test_payload_trace_parts_and_blobs(tmp_path):
    from walter_engine.payload import Trace
    t = Trace(tmp_path / "payload")
    sys_parts = [("soul", "Tu es Walter."), ("environment", "## Environnement\n- Date"),
                 ("mcp_instructions", "W.Alter preface.\n\n## Modules W.Alter\n- memory")]
    system = "\n\n".join(x for _, x in sys_parts)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": "salut"},
                {"role": "user", "content": "<walter-context>\nmémoire\n</walter-context>"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "bash"}}]},
                {"role": "tool", "content": "ok"}]
    tools = [{"type": "function", "function": {"name": "bash", "parameters": {}}}]
    row = t.row(sys_parts=sys_parts, messages=messages, tools=tools,
                usage={"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 40}, "completion_tokens": 5})
    assert set(row["parts"]) == {"soul", "environment", "mcp_preface", "mcp_modules", "tools"}
    assert "sha" not in row["parts"]["environment"] and row["parts"]["tools"]["n"] == 1
    assert row["messages"]["chars"]["pack"] > 0 and row["messages"]["chars"]["owner"] == len("salut")
    assert row["messages"]["last_owner_chars"] == len("salut")
    assert row["usage"] == {"prompt": 100, "cached": 40, "completion": 5}
    blobs = sorted(p.name for p in (tmp_path / "payload" / "blobs").iterdir())
    assert len(blobs) == 4                     # soul, preface, modules, tools: kept once
    t.row(sys_parts=sys_parts, messages=messages, tools=tools, usage={})
    assert sorted(p.name for p in (tmp_path / "payload" / "blobs").iterdir()) == blobs
    t.record({"session": "s"}, sys_parts=sys_parts, messages=messages, tools=tools, usage={})
    assert len(list((tmp_path / "payload").glob("trace-*.jsonl"))) == 1


def test_bench_test_account_judged_autonomous():
    """2026-11-23: a `bench-` test account is judged under `maintenance` (no interactive approval); others stay `test`."""
    from walter_engine.policy import Policy
    p = {"interfaces": {"test": "api", "maintenance": "dev"}, "test_interfaces": {"_doc": "x", "bench-": "maintenance"}}
    assert Policy.test_interface(p, "test", {"kind": "test", "id": "bench-payload"}) == "maintenance"
    assert Policy.test_interface(p, "test", {"kind": "test", "id": "e2e"}) is None
    assert Policy.test_interface(p, "web", {"kind": "owner", "id": "bench-x"}) is None
    assert Policy.test_interface(p, "test", {"kind": "machine", "id": "bench-x"}) is None


# ── system order (payload lot 2, 2026-11-23) ──
def test_the_system_text_puts_the_shared_socle_first_and_the_session_lines_last(engine, tmp_path):
    soul = tmp_path / "soul.md"
    soul.write_text("Tu es Walter.")
    engine.s.instructions = str(soul)
    engine.mcp.instructions = "## Modules W.Alter\n- memory"
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    a._skills0 = "## Skills\n- walter-skills"
    text = engine._system(a)
    assert [k for k, _ in a._sys_parts] == ["soul", "skills_map", "mcp_instructions", "environment", "journal_line"]
    assert text.startswith("Tu es Walter.\n\n## Skills") and text.rstrip().endswith(f"thread_id={a.sid}).")
    b = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    b._skills0 = a._skills0
    shared = text.split("## Environnement")[0]
    assert engine._system(b).startswith(shared)                       # another session shares the whole socle
    engine.s.system_order = "legacy"                                  # rollback: the order before 23/11
    a._sys = None
    engine._system(a)
    assert [k for k, _ in a._sys_parts] == ["soul", "environment", "journal_line", "skills_map", "mcp_instructions"]


# ── prompt layout v2 (lot 3a, 2026-11-24) ──
def _v2_files(engine, tmp_path):
    (tmp_path / "SOUL.md").write_text("<!-- GÉNÉRÉ par walter-soul (engine) -->\nYou are W.Alter.\n")
    (tmp_path / "OPERATING.md").write_text("## Operating rules\n- rule")
    (tmp_path / "CONDUCT.md").write_text("<!-- GÉNÉRÉ par walter-soul (engine-conduct) -->\n## How to work\n- conduct\n")
    (tmp_path / "AGENTS.md").write_text("Tu es Walter (v1).")
    engine.s.instructions, engine.s.soul = str(tmp_path / "AGENTS.md"), str(tmp_path / "SOUL.md")
    engine.s.operating, engine.s.conduct = str(tmp_path / "OPERATING.md"), str(tmp_path / "CONDUCT.md")
    engine.mcp.instructions = "## Modules W.Alter\n- memory"


def test_layout_v2_composes_soul_operating_rules_and_conduct_in_the_shared_socle(engine, tmp_path):
    _v2_files(engine, tmp_path)
    engine.s.prompt_layout = "v2"
    a = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    a._skills0 = "## Skills\n- walter-skills"
    text = engine._system(a)
    assert [k for k, _ in a._sys_parts] == ["soul", "engine_rules", "conduct", "skills_map", "mcp_instructions",
                                           "environment", "journal_line"]
    assert text.startswith("You are W.Alter.\n\n## Operating rules") and "<!--" not in text   # human note stripped
    assert "## Environment\n- Date: " in text and "Monsieur" not in text and "Tu es Walter" not in text
    blocks = engine._messages(a)[0]["content"]
    assert blocks[0]["text"].endswith("- memory") and blocks[1]["text"].startswith("## Environment")
    sub = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"}, depth=1)
    assert "not to the owner" in engine._system(sub)


def test_layout_v2_for_test_accounts_only_and_v1_when_the_soul_is_missing(engine, tmp_path):
    _v2_files(engine, tmp_path)
    engine.s.prompt_layout, engine.s.prompt_layout_test = "v1", "v2"
    owner = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    test = engine.create(cwd="/w", door="api", principal={"kind": "test", "id": "bench-payload"})
    assert engine._system(owner).startswith("Tu es Walter (v1).")
    assert engine._system(test).startswith("You are W.Alter.")
    engine.s.prompt_layout_accounts = {"bench-v1": "v1"}             # a bench arm keeps its own layout
    arm = engine.create(cwd="/w", door="api", principal={"kind": "test", "id": "bench-v1"})
    assert engine._system(arm).startswith("Tu es Walter (v1).")
    (tmp_path / "SOUL.md").unlink()                                   # no Soul file: the v1 profile, never no identity
    test._sys = None
    assert engine._system(test).startswith("Tu es Walter (v1).")


def test_an_edited_soul_reaches_an_open_session_at_its_next_turn_only(engine, tmp_path):
    import os
    _v2_files(engine, tmp_path)
    engine.s.prompt_layout = "v2"
    a = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    a._sys_sig = engine._sys_sources_sig(a)                          # turn start
    first = engine._system(a)
    soul = tmp_path / "SOUL.md"
    soul.write_text("You are W.Alter, edited.\n")
    st = soul.stat()
    os.utime(soul, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert engine._system(a) == first                                 # same turn: stable (cache)
    a._sys_sig = engine._sys_sources_sig(a)                          # next turn start
    assert engine._system(a).startswith("You are W.Alter, edited.")


# ── documentation layer (lot 3c, 2026-11-24) ──
def test_doc_layer_replaces_the_module_layer_keeps_the_walter_call_note_and_follows_the_manifests(engine, tmp_path,
                                                                                                    monkeypatch):
    from walter_engine import engine as eng
    _v2_files(engine, tmp_path)
    engine.mcp.instructions = ("W.Alter base line.\n\n## Modules W.Alter\n- memory\n\n## W.Alter tools not listed\n"
                               "Call them with `walter_call(tool, arguments)`.")
    docs = {"text": "## W.Alter\nW.Alter is a persistent personal intelligence."}
    monkeypatch.setattr(eng, "_doc_layer", lambda form: docs["text"] + f" ({form})")
    engine.s.prompt_layout = "v2"                                     # doc_layer "mcp" by default: unchanged
    a = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    a._skills0 = "## Skills\n- walter-skills"
    a._sys_sig = engine._sys_sources_sig(a)
    assert "## Modules W.Alter" in engine._system(a) and "walter_doc" not in dict(a._sys_parts)
    engine.s.prompt_layout_accounts = {"bench-s2": "v2+s2", "bench-s2n": "v2+s2-skills", "bench-v1": "v1+s2"}
    b = engine.create(cwd="/w", door="api", principal={"kind": "test", "id": "bench-s2"})
    b._skills0 = "## Skills\n- walter-skills"
    b._sys_sig = engine._sys_sources_sig(b)
    text = engine._system(b)
    assert [k for k, _ in b._sys_parts] == ["soul", "engine_rules", "conduct", "walter_doc", "skills_map",
                                           "mcp_instructions", "environment", "journal_line"]
    assert "(s2)" in text and "## Modules W.Alter" not in text and "base line" not in text
    assert dict(b._sys_parts)["mcp_instructions"].startswith("## W.Alter tools not listed")
    assert "(s2)" in engine._messages(b)[0]["content"][0]["text"]     # in the shared, cached socle
    c = engine.create(cwd="/w", door="api", principal={"kind": "test", "id": "bench-s2n"})
    c._skills0 = "## Skills\n- walter-skills"
    c._sys_sig = engine._sys_sources_sig(c)
    engine._system(c)
    assert "skills_map" not in dict(c._sys_parts)
    v1 = engine.create(cwd="/w", door="api", principal={"kind": "test", "id": "bench-v1"})
    v1._sys_sig = engine._sys_sources_sig(v1)
    assert engine._system(v1).startswith("Tu es Walter (v1).") and not v1._doc   # a v2 feature only
    first = engine._system(b)
    docs["text"] = "## W.Alter\nEdited D1."                           # an edited manifest: next turn, not this one
    assert engine._system(b) == first
    b._sys_sig = engine._sys_sources_sig(b)
    assert "Edited D1." in engine._system(b)
    monkeypatch.setattr(eng, "_doc_layer", lambda form: "")           # documentation unavailable: module layer kept
    b._sys_sig = engine._sys_sources_sig(b)
    assert "## Modules W.Alter" in engine._system(b)


def test_doc_layer_from_the_real_presentation_names_walter_and_its_modules():
    from walter_engine import engine as eng
    s1, s2 = eng._doc_layer("s1"), eng._doc_layer("s2")
    if not s2:                                                        # presentation without socle(): before the swap
        return
    assert s1.startswith("## W.Alter") and 'module_guide("walter", depth="D2")' in s1
    assert "### Modules (D1)" in s2 and "`memory`" in s2 and len(s2) > len(s1)


# ── communication profile per recipient (lot 3b, 2026-11-24) ──
def test_the_recipient_is_decided_by_the_session_not_by_the_technical_channel(engine):
    owner = {"kind": "owner", "id": "monsieur"}
    assert engine.recipient(engine.create(cwd="/w", door="web", principal=owner)) == "web"
    assert engine.recipient(engine.create(cwd="/w", door="telegram", principal=owner)) == "telegram"
    assert engine.recipient(engine.create(cwd="/w", door="api", principal=owner)) == "default"   # a person via API
    assert engine.recipient(engine.create(cwd="/w", door="mcp", principal=owner)) == "default"
    assert engine.recipient(engine.create(cwd="/w", door="mcp", principal={"kind": "machine", "id": "guardian"})) == "agent"
    assert engine.recipient(engine.create(cwd="/w", door="telegram", principal=owner, depth=1)) == "agent"   # sub-agent
    assert engine.recipient(engine.create(cwd="/w", door="web", principal={"kind": "test", "id": "e2e"})) == "web"


def test_communication_profile_is_off_by_default_then_its_own_cache_block(engine, tmp_path, monkeypatch):
    import os
    from walter_engine import config as cfg, engine as eng
    _v2_files(engine, tmp_path)
    ifaces = tmp_path / "interfaces"
    for name, text in (("web", "## Communication — Portal\n- tables ok"), ("telegram", "## Communication — Telegram\n- no tables"),
                       ("agent", "## Communication — agent"), ("default", "## Communication — client not known")):
        (ifaces / name).mkdir(parents=True)
        (ifaces / name / "COMMUNICATION.md").write_text(text)
    monkeypatch.setattr(eng, "INTERFACES", ifaces)
    inst = tmp_path / "instance"
    (inst / "config" / "interfaces").mkdir(parents=True)
    monkeypatch.setattr(cfg, "instance_root", lambda: inst)
    engine.s.prompt_layout = "v2"
    web = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    web._sys_sig = engine._sys_sources_sig(web)
    assert "Communication" not in engine._system(web)                 # off by default: unchanged
    engine.s.communication = True
    web._sys_sig = engine._sys_sources_sig(web)
    text = engine._system(web)
    assert [k for k, _ in web._sys_parts][-3:] == ["communication", "environment", "journal_line"]
    assert "tables ok" in text and "no tables" not in text
    blocks = engine._messages(web)[0]["content"]
    assert [("cache_control" in b) for b in blocks] == [True, True, False] and blocks[1]["text"].startswith("## Communication — Portal")
    tg = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    tg._sys_sig = engine._sys_sources_sig(tg)
    tg_blocks = engine._messages(tg)[0]["content"]
    assert tg_blocks[0]["text"] == blocks[0]["text"] and "no tables" in tg_blocks[1]["text"]   # socle shared
    (inst / "config" / "interfaces" / "telegram.md").write_text("- The owner's addition.")   # next turn, this session
    assert "addition" not in engine._system(tg)
    tg._sys_sig = engine._sys_sources_sig(tg)
    assert "- no tables\n\n- The owner's addition." in engine._system(tg)
    engine.s.communication, engine.s.prompt_layout = False, "v1"
    engine.s.prompt_layout_accounts = {"bench-3b": "v2+comm"}         # a bench arm turns it on for itself only
    arm = engine.create(cwd="/w", door="telegram", principal={"kind": "test", "id": "bench-3b"})
    arm._sys_sig = engine._sys_sources_sig(arm)
    assert "no tables" in engine._system(arm)
    v1 = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    v1._sys_sig = engine._sys_sources_sig(v1)
    assert "Communication" not in engine._system(v1)


def test_shipped_profiles_exist_and_inactive_ones_are_never_selected():
    from walter_engine import engine as eng
    for name in ("web", "telegram", "agent", "default"):
        text = (eng.INTERFACES / name / "COMMUNICATION.md").read_text()
        assert text.startswith("## Communication") and "Monsieur" not in text
    for name in ("voice", "desktop"):
        assert (eng.INTERFACES / name / "COMMUNICATION.md").read_text().startswith("<!-- INACTIVE")
        assert name not in eng.DOOR_PROFILE.values()


def test_the_system_message_marks_the_shared_socle_as_its_own_cache_block(engine, tmp_path):
    soul = tmp_path / "soul.md"
    soul.write_text("Tu es Walter.")
    engine.s.instructions = str(soul)
    engine.mcp.instructions = "## Modules W.Alter\n- memory"
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    a._skills0 = "## Skills\n- walter-skills"
    text = engine._system(a)
    blocks = engine._messages(a)[0]["content"]
    assert [b["type"] for b in blocks] == ["text", "text"]
    assert "\n\n".join(b["text"] for b in blocks) == text             # the very text of one string, cut in two
    assert blocks[0]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in blocks[1]
    assert blocks[0]["text"].endswith("- memory") and blocks[1]["text"].startswith("## Environnement")
    b = engine.create(cwd="/w", door="web", principal={"kind": "owner", "id": "monsieur"})
    b._skills0 = a._skills0
    assert engine._messages(b)[0]["content"][0] == blocks[0]          # another session: the same marked socle
    engine.s.system_blocks = False                                    # rollback: one string
    assert engine._messages(a)[0]["content"] == text
    engine.s.system_blocks = True
    engine.s.system_order = "legacy"                                  # the legacy order has no shared prefix to mark
    a._sys = None
    assert isinstance(engine._messages(a)[0]["content"], str)


def test_subagent_on_an_invented_poste_is_refused_at_once_with_the_real_ones(engine, monkeypatch):
    """Lot 3e (27/11): models calling `subagent` from Python guessed postes (« orchestrator », « redaction »); the
    gateway refused them after ~9 s and the delegation was lost. The tool now answers at once with the valid ones."""
    async def postes():
        return {"auto", "general", "coding", "writing"}
    monkeypatch.setattr(engine.llm, "postes", postes)
    seen = {}

    async def run_child(child, prompt, cancel=None):
        seen.update(model=child.model)
        return {"status": "ok", "text": "vu", "tools": 0}
    monkeypatch.setattr(engine, "run_child", run_child)
    a = engine.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    from walter_engine.tools import Exec, agents
    ex = Exec(engine=engine, agent=a, call_id="c1", name="subagent", cancel=asyncio.Event())
    res = asyncio.run(agents.subagent({"description": "x", "prompt": "y", "model": "orchestrator"}, ex))
    assert res.is_error and "coding, general, writing" in res.content and not seen
    res = asyncio.run(agents.subagent({"description": "x", "prompt": "y", "model": "general/L2"}, ex))
    assert not res.is_error and seen["model"] == "general/L2"
