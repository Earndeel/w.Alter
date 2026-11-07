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
