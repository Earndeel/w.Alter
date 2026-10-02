"""P8.2 parsers: Claude Code / Codex transcript lines → canonical events (pure, no database)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "connectors"))
import agent_sessions as A  # noqa: E402

TS = "2026-10-02T10:00:00Z"


def test_claude_human_prompt_answer_and_tool():
    st = {}
    evs = A.parse_claude({"type": "user", "sessionId": "s1", "uuid": "u1", "timestamp": TS, "origin": {"kind": "human"},
                          "message": {"role": "user", "content": "Analyse la VM<system-reminder>secret ctx</system-reminder>"}}, 0, st)
    assert [e["event_type"] for e in evs] == ["conversation.started", "message.sent"]
    assert evs[1]["content"] == "Analyse la VM" and evs[1]["actor"]["is_self"]
    evs = A.parse_claude({"type": "assistant", "sessionId": "s1", "uuid": "a1", "timestamp": TS,
                          "message": {"model": "m", "content": [{"type": "thinking", "thinking": "hidden"},
                                                                 {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                                                                 {"type": "text", "text": "Je regarde."}]}}, 1, st)
    assert [e["event_type"] for e in evs] == ["message.received"] and "hidden" not in evs[0]["content"]
    assert evs[0]["reply_to"] == "msg:u1"
    evs = A.parse_claude({"type": "user", "sessionId": "s1", "uuid": "r1", "timestamp": TS,
                          "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "OUTPUT", "is_error": True}]}}, 2, st)
    assert evs[0]["payload"]["tool"] == "Bash" and evs[0]["payload"]["status"] == "error"
    assert "OUTPUT" not in str(evs[0])                       # outputs are never stored


def test_claude_skips_injected_rows():
    st = {"started": ["s1"]}
    for d in ({"isMeta": True, "message": {"content": "<local-command-caveat>x"}},
              {"isCompactSummary": True, "message": {"content": "This session is being continued"}},
              {"message": {"content": "<command-name>/compact</command-name>"}},
              {"origin": {"kind": "task-notification"}, "message": {"content": "<task-notification>"}}):
        assert A.parse_claude({"type": "user", "sessionId": "s1", "uuid": "x", "timestamp": TS, **d}, 0, st) == []


def test_codex_exec_is_attributed_to_delegator():
    st = {}
    A.parse_codex({"type": "session_meta", "timestamp": TS, "payload": {"id": "c1", "originator": "codex_exec"}}, 0, st)
    evs = A.parse_codex({"type": "event_msg", "timestamp": TS, "payload": {"type": "user_message", "message": "fais X"}}, 10, st)
    assert evs[0]["actor"]["external_id"] == "delegator" and evs[0]["payload"]["automated"]
    A.parse_codex({"type": "response_item", "timestamp": TS, "payload": {"type": "function_call", "name": "shell",
                                                                         "arguments": "{\"cmd\": \"ls\"}", "call_id": "k"}}, 20, st)
    evs = A.parse_codex({"type": "response_item", "timestamp": TS, "payload": {"type": "function_call_output", "call_id": "k",
                                                                               "output": "x" * 50}}, 30, st)
    assert evs[0]["payload"]["tool"] == "shell" and evs[0]["payload"]["output_chars"] == 50
