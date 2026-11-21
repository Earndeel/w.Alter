"""Google AI Pro through the official Antigravity CLI: text only, every CLI tool denied, nothing kept after a call."""
import asyncio
import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from walter_router import paths
from walter_router.analysis import parse
from walter_router.research.prices import antigravity
from walter_router.serve import execution

spec = importlib.util.spec_from_file_location("antigravity_subscription", paths.ROOT / "llm/antigravity_subscription.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)



def _ns(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_ns(v) for v in value]
    return value


@pytest.fixture(autouse=True)
def _litellm_types(monkeypatch):
    """The router's venv has no LiteLLM (walter-llm's has): same field names, plain objects."""
    try:
        import litellm.types.utils  # noqa: F401
        return
    except ImportError:
        pass
    utils = SimpleNamespace(Usage=lambda **kw: SimpleNamespace(**kw),
                            ModelResponse=lambda choices, **kw: SimpleNamespace(choices=_ns(choices), **kw),
                            ModelResponseStream=lambda choices, **kw: SimpleNamespace(
                                choices=[_ns({"finish_reason": None, **c}) for c in choices], **{"usage": None, **kw}))
    for name, module in (("litellm", SimpleNamespace(types=None)), ("litellm.types", SimpleNamespace(utils=utils)),
                         ("litellm.types.utils", utils)):
        monkeypatch.setitem(sys.modules, name, module)


VERIFIED = ["gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low", "claude-sonnet-4-6",
            "claude-opus-4-6-thinking", "gpt-oss-120b-medium"]


def test_offer_key_drops_reasoning_level_and_both_copies_agree():
    for cli_id, base in [("gemini-3.8-flash-high", "gemini-3.8-flash"), ("claude-opus-4-6-thinking", "claude-opus-4-6"),
                         ("gpt-oss-120b-medium", "gpt-oss-120b"), ("claude-sonnet-4-6", "claude-sonnet-4-6")]:
        assert transport.base_id(cli_id) == antigravity.base_id(cli_id) == base


def test_reasoning_level_picks_the_closest_verified_cli_model():
    assert transport.cli_model("gemini-3.8-flash", "low", VERIFIED) == "gemini-3.8-flash-low"
    assert transport.cli_model("gemini-3.8-flash", "xhigh", VERIFIED) == "gemini-3.8-flash-high"
    assert transport.cli_model("gemini-3.8-flash", None, VERIFIED) == "gemini-3.8-flash-high"
    assert transport.cli_model("gemini-3.8-flash", "low", ["gemini-3.8-flash-medium"]) == "gemini-3.8-flash-medium"
    assert transport.cli_model("claude-opus-4-6", "max", VERIFIED) == "claude-opus-4-6-thinking"
    with pytest.raises(transport.TransportError):
        transport.cli_model("gemini-4-pro", "high", VERIFIED)


def test_prompt_keeps_instructions_and_conversation():
    p = transport.prompt_of([{"role": "system", "content": "Sois bref."}, {"role": "user", "content": "A"},
                             {"role": "assistant", "content": "B"}, {"role": "user", "content": "C ?"}])
    assert "<instructions>\nSois bref.\n</instructions>" in p and "[user]\nA" in p and "[assistant]\nB" in p
    assert p.endswith("C ?") and p.startswith(transport.NO_TOOLS)


@pytest.mark.parametrize("messages", [
    [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
     {"role": "tool", "tool_call_id": "1", "content": "y"}, {"role": "user", "content": "z"}],
    [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
])
def test_unsupported_requests_fail_before_any_call(messages):
    with pytest.raises(transport.TransportError):
        transport.prompt_of(messages)


def test_tools_request_is_refused_without_starting_the_cli(tmp_path):
    conf = {"cli": str(tmp_path / "missing-agy"), "home": str(tmp_path), "verified_models": VERIFIED}
    with pytest.raises(transport.TransportError):
        asyncio.run(transport.completion(conf, model="gemini-3.8-flash", messages=[{"role": "user", "content": "x"}],
                                         tools=[{"type": "function", "function": {"name": "f"}}]))


def test_command_denies_every_tool_family_and_ends_with_print_mode():
    cmd = transport._command({"cli": "agy"}, "gemini-3.8-flash-low", None, 60)
    deny = json.loads(cmd[cmd.index("--settings") + 1])["permissions"]["deny"]
    assert {"read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)", "command(*)", "mcp(*)"} <= set(deny)
    assert cmd[-1] == "-p=" and "--sandbox" in cmd and "--dangerously-skip-permissions" not in cmd


def fake_cli(tmp_path: Path, events: list[dict]) -> dict:
    """A stand-in `agy` that checks its environment, writes conversation files like the real CLI and prints events."""
    home = tmp_path / "home"
    state = home / ".gemini" / "antigravity-cli"
    for sub in ("conversations", "brain", "annotations", "presence", "implicit"):
        (state / sub).mkdir(parents=True)
    (tmp_path / "events.json").write_text(json.dumps(events))
    cli = tmp_path / "agy"
    cli.write_text(f"""#!/usr/bin/env python3
import json, os, sys
assert "OPENROUTER_API_KEY" not in os.environ and os.environ["HOME"] == {str(home)!r}
json.loads(sys.stdin.readline())
s = os.path.join(os.environ["HOME"], ".gemini", "antigravity-cli")
events = json.load(open({str(tmp_path / "events.json")!r}))
conv = events[-1]["result"]["conversation_id"]
open(os.path.join(s, "conversations", conv + ".db"), "w").write("prompt")
os.makedirs(os.path.join(s, "brain", conv))
open(os.path.join(s, "conversation_summaries.db"), "w").write("summary")
for e in events:
    print(json.dumps(e))
""")
    cli.chmod(0o700)
    return {"cli": str(cli), "home": str(home), "verified_models": VERIFIED, "timeout": 30}


def events(conv="0f8b6c1e-0000-4000-8000-000000000001", text="Bonjour", status="SUCCESS"):
    return [{"event": "step_update", "step_update": {"conversation_id": conv, "step_type": "agent_response",
                                                     "text_delta": text}},
            {"event": "result", "result": {"conversation_id": conv, "status": status, "response": text,
                                           "usage": {"input_tokens": 7000, "output_tokens": 2, "total_tokens": 7002}}}]


def test_answer_and_nothing_left_on_disk(tmp_path):
    conf = fake_cli(tmp_path, events())
    r = asyncio.run(transport.completion(conf, model="gemini-3.8-flash", messages=[{"role": "user", "content": "x"}]))
    assert r.choices[0].message.content == "Bonjour" and r.model == "gemini-3.8-flash" and r.usage.prompt_tokens == 7000
    state = Path(conf["home"]) / ".gemini" / "antigravity-cli"
    assert not any((state / "conversations").iterdir()) and not any((state / "brain").iterdir())
    assert not (state / "conversation_summaries.db").exists() and not any((Path(conf["home"]) / "calls").iterdir())


def test_stream_yields_text_then_usage(tmp_path):
    conf = fake_cli(tmp_path, events(text="Salut"))

    async def run():
        it = await transport.completion(conf, model="gemini-3.8-flash", stream=True,
                                        messages=[{"role": "user", "content": "x"}])
        return [c async for c in it]
    chunks = asyncio.run(run())
    assert chunks[0].choices[0].delta.content == "Salut" and chunks[-1].choices[0].finish_reason == "stop"
    assert chunks[-1].usage.prompt_tokens == 7000


def test_failed_run_raises(tmp_path):
    conf = fake_cli(tmp_path, events(text="", status="ERROR"))
    with pytest.raises(transport.TransportError):
        asyncio.run(transport.completion(conf, model="gemini-3.8-flash", messages=[{"role": "user", "content": "x"}]))


def test_offers_are_subscription_text_offers_run_by_walter_llm_only():
    rows = parse.parse_offers("antigravity", {"models": ["gemini-3.8-flash"], "efforts": {"gemini-3.8-flash": ["low"]}})
    assert len(rows) == 1 and rows[0]["model_id"] == "gemini-3-8-flash" and rows[0]["access"] == "subscription"
    assert rows[0]["pricing"]["tools"] is False and rows[0]["pricing"]["efforts"] == ["low"]
    assert execution._runnable(rows[0]) == (None, "gemini-3.8-flash", "antigravity")


def test_native_only_never_reaches_hermes():
    offer = {"provider": "antigravity", "offer_key": "gemini-3.8-flash", "model_id": "gemini-3-8-flash",
             "interface": "chat", "pricing": {}}
    assert execution._runnable(offer) == (None, "gemini-3.8-flash", "antigravity")
