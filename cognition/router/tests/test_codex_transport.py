"""Codex (ChatGPT subscription) transport details owned by walter-llm, offline."""
import ast
import json
import uuid
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "llm" / "gateway.py"


def _functions(*names):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def test_cache_session_is_stable_per_conversation_or_prefix_and_hashed():
    f = _functions("codex_cache_session")["codex_cache_session"]
    body = {"messages": [{"role": "system", "content": "Extrais les faits."}, {"role": "user", "content": "a"}]}
    other = {"messages": [{"role": "system", "content": "Extrais les faits."}, {"role": "user", "content": "b"}]}
    a = f("walter-memory", "memory_extraction", body, {})
    assert a == f("walter-memory", "memory_extraction/L1", other, {})        # same caller and instructions
    assert a != f("walter-memory", "summarization", body, {})
    assert a != f("walter-memory", "memory_extraction",
                  {"messages": [{"role": "system", "content": "Autre consigne."}]}, {})
    s = f("dsh", "general", body, {"session_id": "dsh/vm/session-x"})
    assert s == f("dsh", "coding", other, {"session_id": "dsh/vm/session-x"})  # a conversation keeps its id
    assert "session-x" not in s and uuid.UUID(s)                              # never an internal identifier


def test_parallel_call_arguments_come_from_their_done_events():
    T = pytest.importorskip("litellm.completion_extras.litellm_responses_transformation.transformation")
    _functions("_install_codex_stream_arguments")["_install_codex_stream_arguments"]()
    it = T.OpenAiResponsesToChatCompletionStreamIterator(iter(()), sync_stream=True)
    events = []
    for i, (name, args) in enumerate((("weather", '{"city": "Paris"}'), ("clock", '{"tz": "Europe/Paris"}'))):
        call = {"type": "function_call", "id": f"fc_{i}", "call_id": f"call_{i}", "name": name, "arguments": ""}
        events += [{"type": "response.output_item.added", "output_index": i, "item": call},
                   {"type": "response.function_call_arguments.done", "output_index": i, "arguments": args},
                   {"type": "response.output_item.done", "output_index": i, "item": {**call, "arguments": args}}]
    single = {"type": "function_call", "id": "fc_9", "call_id": "call_9", "name": "weather", "arguments": ""}
    events += [{"type": "response.output_item.added", "output_index": 2, "item": single},
               {"type": "response.function_call_arguments.delta", "output_index": 2, "delta": '{"city":"Lyon"}'},
               {"type": "response.output_item.done", "output_index": 2, "item": {**single, "arguments": '{"city":"Lyon"}'}}]
    got = {}
    for ev in events:
        chunk = it.chunk_parser(ev)
        for tc in (chunk.choices[0].delta.tool_calls or []) if chunk.choices else []:
            fn = tc["function"] if isinstance(tc, dict) else tc.function
            args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            idx = tc["index"] if isinstance(tc, dict) else tc.index
            got[idx] = got.get(idx, "") + (args or "")
    assert got == {0: '{"city": "Paris"}', 1: '{"tz": "Europe/Paris"}', 2: '{"city":"Lyon"}'}   # streamed once only


BASE = "You are a coding agent."


def test_custom_instructions_open_the_input_as_a_developer_item_and_carry_the_cache_key():
    """2026-11-23 (payload lot 2): text after the required base instructions was never cached by the backend."""
    f = _functions("codex_cache_request")["codex_cache_request"]
    user = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "salut"}]}
    req = f({"instructions": BASE + "\n\nTu es W.Alter.", "input": [user], "tools": []}, "sess-1", BASE)
    assert req["instructions"] == BASE
    assert req["input"][0] == {"type": "message", "role": "developer",
                               "content": [{"type": "input_text", "text": "Tu es W.Alter."}]}
    assert req["input"][1] == user and req["prompt_cache_key"] == "sess-1"


def test_cache_request_leaves_what_it_cannot_or_must_not_move():
    f = _functions("codex_cache_request")["codex_cache_request"]
    only_base = f({"instructions": BASE, "input": []}, None, BASE)
    assert only_base == {"instructions": BASE, "input": []}                           # nothing to move, no session
    foreign = f({"instructions": "Autre texte.", "input": []}, "s", BASE)
    assert foreign["instructions"] == "Autre texte." and foreign["input"] == []        # not the expected shape
    off = f({"instructions": BASE + "\n\nX", "input": []}, "s", BASE,
            {"developer_instructions": False, "prompt_cache_key": False})
    assert off == {"instructions": BASE + "\n\nX", "input": []}                         # both switches off: as before


def test_litellm_codex_text_can_be_dropped_for_an_empty_instructions_field():
    """2026-11-25 (Monsieur): LiteLLM's Codex CLI text is ours, not the backend's; an empty field is accepted."""
    f = _functions("codex_cache_request")["codex_cache_request"]
    empty = {"base_instructions": "empty"}
    user = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "salut"}]}
    req = f({"instructions": BASE + "\n\nTu es W.Alter.", "input": [user]}, "s", BASE, empty)
    assert req["instructions"] == "" and req["input"][0]["content"][0]["text"] == "Tu es W.Alter."
    assert f({"instructions": BASE, "input": []}, None, BASE, empty)["instructions"] == ""     # no caller text
    alone = f({"instructions": BASE + "\n\nX", "input": []}, None, BASE, {**empty, "developer_instructions": False})
    assert alone["instructions"] == "X"                                  # the caller's text stays, without the base
    assert f({"instructions": "Autre texte.", "input": []}, None, BASE, empty)["instructions"] == "Autre texte."


def test_cache_key_names_only_the_part_every_session_shares():
    """2026-11-25: the engine marks its socle (and communication profile); a session's own lines never enter the key,
    whatever the socle's length (lot 3c s1: 9 % cached when they did)."""
    f = _functions("codex_cache_session")["codex_cache_session"]
    mark = {"cache_control": {"type": "ephemeral"}}

    def body(socle, lines):
        return {"messages": [{"role": "system", "content": [{"type": "text", "text": socle, **mark},
                                                            {"type": "text", "text": "Profil web.", **mark},
                                                            {"type": "text", "text": lines}]}]}
    short = "Tu es W.Alter."                                                     # far below 8 000 chars
    a = f("walter", "general", body(short, "Session A, 10:02"), {})
    assert a == f("walter", "general", body(short, "Session B, 17:40"), {})
    assert a != f("walter", "general", body(short + " Autre socle.", "Session A, 10:02"), {})
    unmarked = {"messages": [{"role": "system", "content": [{"type": "text", "text": short},
                                                            {"type": "text", "text": "Session A"}]}]}
    assert f("walter", "general", unmarked, {}) != f("walter", "general", {"messages": [
        {"role": "system", "content": [{"type": "text", "text": short}, {"type": "text", "text": "Session B"}]}]}, {})


def test_installed_transform_applies_to_litellm_chatgpt_requests():
    RT = pytest.importorskip("litellm.llms.chatgpt.responses.transformation")
    from litellm.llms.chatgpt.common_utils import get_chatgpt_default_instructions
    from litellm.types.router import GenericLiteLLMParams
    ns = _functions("codex_cache_request", "_install_codex_prompt_cache")
    ns["_CONF"] = {}
    ns["_install_codex_prompt_cache"]()
    ns["_install_codex_prompt_cache"]()                                                  # idempotent
    assert RT.ChatGPTResponsesAPIConfig.transform_responses_api_request._walter_cache
    cfg = RT.ChatGPTResponsesAPIConfig()
    req = cfg.transform_responses_api_request(
        "gpt-x", [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "a"}]}],
        {"instructions": "Tu es W.Alter."}, GenericLiteLLMParams(litellm_session_id="sess-2"), {})
    assert req["instructions"] == get_chatgpt_default_instructions()
    assert req["input"][0]["role"] == "developer" and req["prompt_cache_key"] == "sess-2"
    bare = cfg.transform_responses_api_request("gpt-x", [], {"instructions": "Tu es W.Alter."},
                                               GenericLiteLLMParams(), {})
    assert "prompt_cache_key" not in bare                                     # never LiteLLM's per-call fallback id


# ── one payload, two cache systems (2026-11-24) ──
def _layout():
    ns = _functions("anthropic_protocol", "_all_text_parts", "_unmarked", "cache_layout")
    ns["KIE_GPT"] = ("gpt-",)
    ns["_CONF"] = {}
    return ns


SOCLE = [{"type": "text", "text": "Tu es Walter.", "cache_control": {"type": "ephemeral"}},
         {"type": "text", "text": "## Environnement\n- Date : 2026-11-24 (UTC)"}]


def test_claude_routes_are_recognised_on_every_provider():
    f = _layout()["anthropic_protocol"]
    assert f({"provider": "claude-pro", "model": "claude-haiku-5-5"})
    assert f({"provider": "kie", "model": "claude-opus-5-5"}) and not f({"provider": "kie", "model": "gpt-6.2-sol"})
    assert f({"provider": "openrouter", "model": "anthropic/claude-opus-5.5"})
    assert not f({"provider": "openrouter", "model": "deepseek/deepseek-v4"}) and not f({"provider": "codex", "model": "gpt-6.2"})


def test_a_one_shot_claude_call_marks_its_system_only_a_conversation_also_its_last_message():
    f = _layout()["cache_layout"]
    claude = {"provider": "claude-pro", "model": "claude-haiku-5-5"}
    one = f(claude, {"messages": [{"role": "system", "content": "Règles"}, {"role": "user", "content": "x"}]})
    assert one["cache_control_injection_points"] == [{"location": "message", "role": "system"}]
    talk = f(claude, {"messages": [{"role": "system", "content": SOCLE}, {"role": "user", "content": "a"},
                                   {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]})
    assert talk["cache_control_injection_points"] == [{"location": "message", "role": "system"},
                                                      {"location": "message", "index": -1}]
    tools = f(claude, {"messages": [{"role": "user", "content": "a"}], "tools": [{"type": "function"}]})
    assert {"location": "message", "index": -1} in tools["cache_control_injection_points"]
    assert talk["messages"][0]["content"] is SOCLE                       # the caller's socle marker is kept
    off = f(claude, {"messages": [{"role": "user", "content": "a"}]}, {"enabled": False})
    assert "cache_control_injection_points" not in off


def test_openai_protocols_get_back_the_exact_text_without_markers():
    f = _layout()["cache_layout"]
    body = {"messages": [{"role": "system", "content": SOCLE},
                         {"role": "user", "content": [{"type": "text", "text": "q", "cache_control": {"type": "ephemeral"}},
                                                      {"type": "image_url", "image_url": {"url": "data:x"}}]}],
            "cache_control_injection_points": [{"location": "message", "role": "system"}]}
    out = f({"provider": "codex", "model": "gpt-6.2-sol"}, dict(body))
    assert out["messages"][0] == {"role": "system", "content": "Tu es Walter.\n\n## Environnement\n- Date : 2026-11-24 (UTC)"}
    assert out["messages"][1]["content"] == [{"type": "text", "text": "q"}, {"type": "image_url", "image_url": {"url": "data:x"}}]
    assert "cache_control_injection_points" not in out
    assert SOCLE[0]["cache_control"]                                     # the caller's payload is not modified
    plain = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}
    assert f({"provider": "openrouter", "model": "deepseek/deepseek-v4"}, dict(plain))["messages"] is plain["messages"]


def test_the_codex_cache_key_of_two_blocks_is_the_key_of_their_marked_socle():
    """Until 2026-11-25 two blocks gave the key of their joined text; now only the marked socle names it (the
    session's own lines, here the date, stay out of the key)."""
    f = _functions("codex_cache_session")["codex_cache_session"]
    blocks = f("walter-engine", "general", {"messages": [{"role": "system", "content": SOCLE}]}, {})
    socle = SOCLE[0]["text"]
    assert blocks == f("walter-engine", "general", {"messages": [{"role": "system", "content": socle}]}, {})


def test_a_caller_marked_system_reaches_anthropic_with_one_marker_on_the_socle():
    H = pytest.importorskip("litellm.integrations.anthropic_cache_control_hook").AnthropicCacheControlHook
    T = pytest.importorskip("litellm.llms.anthropic.chat.transformation").AnthropicConfig
    f = _layout()["cache_layout"]
    import copy
    kw = f({"provider": "claude-pro", "model": "claude-haiku-5-5"},
           {"messages": [{"role": "system", "content": copy.deepcopy(SOCLE)}, {"role": "user", "content": "a"},
                         {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]})
    _, msgs, _ = H().get_chat_completion_prompt(
        model="claude-haiku-5-5", messages=kw["messages"],
        non_default_params={"cache_control_injection_points": kw["cache_control_injection_points"]},
        prompt_id=None, prompt_variables=None, dynamic_callback_params={})
    body = T().transform_request("claude-haiku-5-5", msgs, {"max_tokens": 10}, {}, {})
    assert [b.get("cache_control") for b in body["system"]] == [{"type": "ephemeral"}, None]
    assert [b["text"] for b in body["system"]] == [p["text"] for p in SOCLE]
    assert "cache_control" in json.dumps(body["messages"][-1])           # the conversation's rolling point
    assert json.dumps(body).count("cache_control") == 2                  # two of the four allowed
