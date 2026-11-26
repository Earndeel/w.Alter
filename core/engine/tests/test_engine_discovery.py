"""Lot 3e step 3 (2026-11-26): the engine's catalogue, search and contracts, the same from Python as from any door.
Offline: witness tools, no network, no model, no module presentation read."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_engine import config  # noqa: E402
from walter_engine.tools import Registry, Result, Tool, builtin, discovery, obj  # noqa: E402

W = "mcp__walter__"


async def _noop(args, ex):
    return Result("ok")


def _registry(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery(), "cards_path", lambda: tmp_path / "cards.json")
    reg = Registry()
    reg._module_texts = {"vault": "- `vault_search(text)` — scanned receipts", "vault:d1": "Raw files of a life."}
    builtin.register(reg)
    reg.add(Tool(W + "walter_health", "Is everything working? Status and health of the stack.", obj({}), _noop,
                 source="mcp:walter", module="core", spec={"effects": ["none"], "concurrency": "parallel"}))
    reg.add(Tool(W + "vault_search", "Search the Raw Vault: photos and documents.", obj({"text": {"type": "string"}}),
                 _noop, source="mcp:walter", hidden=True, module="vault",
                 spec={"effects": ["none"], "concurrency": "parallel", "produces": ["object"]}))
    return reg


def test_search_finds_a_tool_from_a_french_need_with_its_owner(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch)
    top = reg.search("vérifie si tout fonctionne", 3)[0]
    assert top["name"] == W + "walter_health" and top["module"] == "core" and top["effects"] == ["none"]
    assert reg.search("retrouve le reçu", 1)[0]["name"] == W + "vault_search"     # the module guide's line
    assert all(r["name"] != "python" for r in reg.search("run python code", 50))


def test_the_index_follows_tool_and_intent_changes(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch)
    assert reg.search("brouillon", 3) == []
    d = discovery()
    tool = reg._entry(reg.tools["write"])
    d.save_intents(d.parse_generated(json.dumps({"cards": {"write": {"intents_fr": ["garde ce brouillon"]}}}), [tool]))
    assert reg.search("brouillon", 1)[0]["name"] == "write"                      # new intents are picked up
    reg.tools["write"].description = "Write a file, reworded."
    assert reg.search("brouillon", 1) == []                                     # stale: ignored until regenerated


def test_describe_gives_the_whole_contract(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch)
    rec = reg.describe(W + "vault_search")
    assert rec["module"] == "vault" and rec["effects"] == ["none"] and rec["produces"] == ["object"]
    assert rec["parameters"]["properties"] == {"text": {"type": "string"}}
    native = reg.describe("write")
    assert native["module"] == "core" and native["concurrency"] == {"resource": "file", "key": "file_path"}


def test_the_catalog_lists_every_reachable_tool_by_owner(tmp_path, monkeypatch):
    reg = _registry(tmp_path, monkeypatch)
    cat = reg.catalog()
    rows = {r["name"]: r for r in cat["tools"]}
    assert rows[W + "vault_search"]["offered_to_model"] is False                # Python-only tools are listed too
    assert rows["write"]["module"] == "core"
    assert {"module": "vault", "summary": "Raw files of a life."} in cat["modules"]
    assert [r["name"] for r in reg.catalog("vault")["tools"]] == [W + "vault_search"]


def test_python_reaches_catalog_search_and_contracts_through_the_host(tmp_path, monkeypatch):
    from walter_engine import engine as E
    from walter_engine.tools.python import Kernel
    eng = E.Engine(config.Settings(state=tmp_path / "state", trusted_hosts=["portal.example"],
                                   login_url_file=tmp_path / "login-url", web_cookie_days=365))
    monkeypatch.setattr(discovery(), "cards_path", lambda: tmp_path / "cards.json")
    eng.registry = _registry(tmp_path, monkeypatch)
    agent = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    k = Kernel(eng.python, agent)
    sent = []
    k.send = sent.append

    async def ask(method, params):
        await k.on_host({"id": method, "method": method, "params": params})
        return sent[-1]
    cat = asyncio.run(ask("catalog", {"module": "vault"}))
    found = asyncio.run(ask("search", {"query": "raw vault", "limit": 2}))
    rec = asyncio.run(ask("describe", {"name": "vault_search"}))               # the short name works too
    assert cat["ok"] and cat["result"]["tools"][0]["name"] == W + "vault_search"
    assert found["ok"] and found["result"][0]["name"] == W + "vault_search"
    assert rec["ok"] and rec["result"]["module"] == "vault"
    asyncio.run(eng.doors.close())
    asyncio.run(eng.llm.close())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
