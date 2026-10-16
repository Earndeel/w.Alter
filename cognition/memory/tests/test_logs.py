"""walter-logs: secret masking and transcript parsers (pure, no database)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import logs as L  # noqa: E402

TS = "2026-10-04T10:00:00Z"


class FakeWriter(L.Writer):
    """Writer without a database: records events in memory."""

    def __init__(self):
        self.sess, self.rows, self.calls, self.dirty, self.inserted, self.events = {}, [], {}, set(), 0, []

    def session(self, session_id, *, runtime, native_id, privacy_class="cloud_allowed", **fields):
        s = self.sess.setdefault(session_id, {"seq": 0, "turns": 0, "privacy": privacy_class, "runtime": runtime,
                                              "last": None, "fields": {}})
        s["fields"].update({k: v for k, v in fields.items() if v is not None})
        return s

    def add(self, session_id, type_, occurred_at, source_ref, *, text=None, call_id=None, tool=None, model=None,
            status=None, data=None, human=False):
        s = self.sess[session_id]
        s["turns"] += human
        s["seq"] += 1
        if type_ == "tool/call" and call_id and tool:
            self.calls[call_id] = tool
        self.events.append({"session": session_id, "seq": s["seq"], "type": type_, "text": L.mask(text) if text else None,
                            "call_id": call_id, "tool": tool, "status": status, "turn": s["turns"], "data": data})

    def tool_of(self, call_id):
        return self.calls.get(call_id)


def test_mask_keeps_names_drops_values_and_is_idempotent():
    cases = {
        "OPENROUTER_API_KEY=sk-or-v1-" + "a" * 40: "OPENROUTER_API_KEY=«secret:api_key»",
        'export CLOUDFLARE_AI_TOKEN="abcdEFGH1234567890xyz"': 'export CLOUDFLARE_AI_TOKEN="«secret»"',
        '{"api_key": "<secret:redacted>"}': '{"api_key": "«secret:api_key»"}',
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123": "Authorization: Bearer «secret»",
        "postgresql://hindsight:Sup3rS3cret@127.0.0.1:5433/db": "postgresql://hindsight:«secret»@127.0.0.1:5433/db",
        "mot de passe: Hunter2024": "mot de passe: «secret:password»",
        "max_tokens=2048 et token_count 1234": "max_tokens=2048 et token_count 1234",
    }
    for raw, want in cases.items():
        assert L.mask(raw) == want, raw
        assert L.mask(L.mask(raw)) == want


def test_claude_flow_reasoning_call_result_and_turns():
    w, st = FakeWriter(), {}
    L.parse_claude(w, {"type": "user", "sessionId": "s1", "timestamp": TS, "origin": {"kind": "human"},
                       "message": {"content": "Liste les fichiers"}}, "o0", st)
    L.parse_claude(w, {"type": "assistant", "sessionId": "s1", "timestamp": TS,
                       "message": {"model": "claude-x", "content": [
                           {"type": "thinking", "thinking": "je vais lancer ls"},
                           {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}}, "o1", st)
    L.parse_claude(w, {"type": "user", "sessionId": "s1", "timestamp": TS,
                       "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt\nb.txt"}]}},
                   "o2", st)
    L.parse_claude(w, {"type": "user", "sessionId": "s1", "timestamp": TS, "isMeta": True,
                       "message": {"content": "<local-command-stdout>x</local-command-stdout>"}}, "o3", st)
    types = [e["type"] for e in w.events]
    assert types == ["user/message", "assistant/reasoning", "tool/call", "tool/result", "user/message"]
    res = w.events[3]
    assert res["tool"] == "Bash" and res["call_id"] == "t1" and res["text"] == "a.txt\nb.txt" and res["status"] == "ok"
    assert w.events[1]["text"] == "je vais lancer ls"
    assert w.events[4]["data"]["injected"] and w.sess["claude_code/vm/s1"]["turns"] == 1


def test_claude_sidechain_is_a_child_session():
    w, st = FakeWriter(), {}
    L.parse_claude(w, {"type": "assistant", "sessionId": "s1", "isSidechain": True, "agentId": "ag", "timestamp": TS,
                       "message": {"content": [{"type": "text", "text": "sous-agent"}]}}, "o0", st)
    s = w.sess["claude_code/vm/s1:ag"]
    assert s["fields"]["parent_session_id"] == "claude_code/vm/s1"


def test_codex_flow():
    w, st = FakeWriter(), {}
    lines = [
        {"type": "session_meta", "timestamp": TS, "payload": {"id": "c1", "originator": "codex_exec", "cwd": "/root"}},
        {"type": "turn_context", "timestamp": TS, "payload": {"model": "gpt-6-luna", "effort": "max"}},
        {"type": "event_msg", "timestamp": TS, "payload": {"type": "user_message", "message": "Fais X"}},
        {"type": "event_msg", "timestamp": TS, "payload": {"type": "agent_reasoning", "text": "plan"}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "function_call", "call_id": "f1", "name": "shell",
                                                               "arguments": "{\"cmd\": \"ls\"}"}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "function_call_output", "call_id": "f1",
                                                               "output": "ok"}},
        {"type": "event_msg", "timestamp": TS, "payload": {"type": "agent_message", "message": "Fait."}},
    ]
    for i, d in enumerate(lines):
        L.parse_codex(w, d, f"o{i}", st)
    assert [e["type"] for e in w.events] == ["model/selection", "user/message", "assistant/reasoning", "tool/call",
                                             "tool/result", "assistant/message"]
    assert w.events[4]["tool"] == "shell" and w.events[4]["text"] == "ok"
    assert "codex/codex_exec/c1" in w.sess


def test_show_respects_privacy():
    assert L._show("x", "local_only", "cloud_allowed") == "[contenu local uniquement]"
    assert L._show("appelle +33 6 12 34 56 78", "redacted_cloud", "cloud_allowed") == "appelle [PHONE_1]"
    assert L._show("abc", "local_only", "local_only") == "abc"
    assert L._title("Titre", "local_only", "cloud_allowed") == "[session locale]"


def test_masked_password_does_not_retrigger_detector():
    from walter_memory import privacy
    masked = L.mask("mot de passe: Hunter2024")
    assert ("secret", "password_stmt") in privacy.detect(masked)          # the raw detector would fire
    assert not privacy.detect(L._MASKED.sub("", masked))                   # what classify() actually checks


def test_codex_desktop_format_messages_and_encrypted_reasoning():
    """Codex Desktop (2026-10): messages only as response_item messages; injected AGENTS.md; encrypted reasoning."""
    w, st = FakeWriter(), {}
    lines = [
        {"type": "session_meta", "timestamp": TS, "payload": {"id": "d1", "originator": "Codex Desktop"}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "message", "role": "user",
                                                               "content": [{"type": "input_text", "text": "# AGENTS.md instructions\n..."}]}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "message", "role": "user",
                                                               "content": [{"type": "input_text", "text": "Calcule mon usage"}]}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "reasoning", "summary": [], "encrypted_content": "gAAA"}},
        {"type": "response_item", "timestamp": TS, "payload": {"type": "message", "role": "assistant",
                                                               "content": [{"type": "output_text", "text": "Voici."}]}},
        {"type": "event_msg", "timestamp": TS, "payload": {"type": "agent_message", "message": "Voici."}},   # duplicate
    ]
    for i, d in enumerate(lines):
        L.parse_codex(w, d, f"o{i}", st)
    assert [e["type"] for e in w.events] == ["user/message", "user/message", "assistant/reasoning", "assistant/message"]
    assert w.events[0]["data"] == {"injected": True} and w.events[1]["turn"] == 1
    assert w.events[2]["data"]["encrypted"] is True
