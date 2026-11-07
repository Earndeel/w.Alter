import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("kie_compat", Path(__file__).with_name("__init__.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_drops_output_config_for_kie_claude_only():
    req = {"model": "claude-opus-5-5", "thinking": {"type": "adaptive"}, "output_config": {"effort": "max"}}
    out = m._strip_output_config(request=req, base_url="https://api.kie.ai/claude", api_mode="anthropic_messages")
    assert "output_config" not in out["request"] and out["request"]["thinking"] == {"type": "adaptive"}
    assert m._strip_output_config(request=req, base_url="https://api.anthropic.com", api_mode="anthropic_messages") is None
    assert m._strip_output_config(request={"model": "x"}, base_url="https://api.kie.ai/claude") is None
