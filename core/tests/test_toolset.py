"""Lot 3 C11 (2026-11-07): a client may list only a core set of Walter tools; the others stay reachable through
`walter_call`, with their own validation, and the set is fixed for the life of the server process."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import walter_capabilities as capabilities


def server():
    mcp = FastMCP("t")

    @mcp.tool()
    def memory_search(query: str) -> str:
        """Search memory.

        Long explanation that only matters when the tool is used."""
        return "found " + query

    @mcp.tool()
    def vault_get(object_id: str, limit: int = 3) -> str:
        """Fetch one raw object."""
        return f"{object_id}:{limit}"

    @mcp.tool()
    def walter_plans() -> str:
        """Plans."""
        return "plans"
    return mcp


def names(mcp):
    return sorted(t.name for t in mcp._tool_manager.list_tools())


def run(coro):
    return asyncio.run(coro)


def test_all_toolset_changes_nothing():
    mcp = server()
    assert capabilities.apply_toolset(mcp, None) == []
    assert names(mcp) == ["memory_search", "vault_get", "walter_plans"]


def test_core_toolset_hides_the_rest_behind_one_generic_call():
    mcp = server()
    hidden = capabilities.apply_toolset(mcp, ["memory_search", "not_registered"])
    assert hidden == ["vault_get", "walter_plans"]
    assert names(mcp) == ["memory_search", "walter_call"]
    call = mcp._tool_manager.get_tool("walter_call")
    listing = json.loads(run(call.run({})))
    assert [t["name"] for t in listing["tools"]] == ["vault_get", "walter_plans"]
    assert listing["tools"][0]["summary"] == "Fetch one raw object."
    described = json.loads(run(call.run({"tool": "vault_get", "describe": True})))
    assert described["parameters"]["required"] == ["object_id"] and "Fetch one raw object" in described["description"]
    assert run(call.run({"tool": "vault_get", "arguments": {"object_id": "o1"}})) == "o1:3"


def test_generic_call_keeps_each_tool_validation_and_refuses_unknown_or_listed_tools():
    mcp = server()
    capabilities.apply_toolset(mcp, ["memory_search"])
    call = mcp._tool_manager.get_tool("walter_call")
    with pytest.raises(ToolError):
        run(call.run({"tool": "vault_get", "arguments": {"limit": "x"}}))
    for tool in ("unknown", "memory_search", "walter_call"):   # listed tools are called directly, never twice
        assert json.loads(run(call.run({"tool": tool, "arguments": {}})))["error"] == "not_a_hidden_tool"


def test_profile_comes_from_client_config_and_env_overrides_it(tmp_path, monkeypatch):
    conf = tmp_path / "toolsets.toml"
    conf.write_text('[toolsets]\ncore = ["memory_search"]\n\n[clients.dsh]\ntoolset = "core"\nmodule_layer = "m0"\n')
    monkeypatch.delenv("WALTER_TOOLSET", raising=False)
    monkeypatch.delenv("WALTER_MODULE_LAYER", raising=False)
    assert capabilities.client_profile("dsh", conf) == {"toolset": ["memory_search"], "module_layer": "m0", "name": "core"}
    assert capabilities.client_profile("claude", conf) == {"toolset": None, "module_layer": "full", "name": "all"}
    monkeypatch.setenv("WALTER_TOOLSET", "core")
    monkeypatch.setenv("WALTER_MODULE_LAYER", "m0")
    assert capabilities.client_profile("codex", conf)["toolset"] == ["memory_search"]
    monkeypatch.setenv("WALTER_TOOLSET", "unknown")
    with pytest.raises(ValueError):
        capabilities.client_profile("codex", conf)
