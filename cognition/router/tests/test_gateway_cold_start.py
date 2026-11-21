"""walter-llm cold start (18/11): the decision path is warmed first, and a key is read from Bitwarden once even
when the start-up warm and a first call ask for it together."""
import ast
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
import structured  # noqa: E402


def _gateway(monkeypatch, read_s=0.2):
    source = LLM / "gateway.py"
    tree = ast.parse(source.read_text())
    names = {"provider_key", "_read_key", "warm_decisions"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    reads = []

    def env_value(name, consumer):
        reads.append(name)
        time.sleep(read_s)
        return f"value-of-{name}"
    monkeypatch.setitem(sys.modules, "walter_secrets", SimpleNamespace(grants=SimpleNamespace(env_value=env_value)))
    ns = {"time": time, "threading": threading, "_keys": {}, "_keys_lock": threading.Lock(), "_reading": {},
          "KEY_TTL": 600, "KEY_WAIT_S": 5,
          "WARMED": {"started": None, "decisions_ms": None, "keys": {}, "done_ms": None},
          "decision_chain": lambda: ["nace/drex-max-v1.1", "liquidai/d1.2-ultra", "liquid/d1.2-ultra",
                                     "cloudflare/clef"],
          "decision_signals": lambda: {"signals": []}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns, reads


def test_a_key_asked_twice_at_once_is_read_once(monkeypatch):
    ns, reads = _gateway(monkeypatch)
    got = []
    ts = [threading.Thread(target=lambda: got.append(ns["provider_key"]("LIQUID_API_KEY"))) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert reads == ["LIQUID_API_KEY"] and got == ["value-of-LIQUID_API_KEY"] * 4


def test_the_warm_reads_every_key_a_decision_route_reads(monkeypatch):
    ns, reads = _gateway(monkeypatch, read_s=0)
    ns["warm_decisions"]()
    assert reads == ["NACE_API_KEY", "LIQUID_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_ACCOUNT_ID",
                     "CLOUDFLARE_AI_TOKEN"]
    assert ns["WARMED"]["decisions_ms"] is not None and set(ns["WARMED"]["keys"]) == set(reads)


def test_every_decision_route_says_its_keys():
    for model in ("nace/drex-max-v1.1", "liquidai/d1.2-ultra", "liquid/d1.2-ultra", "cloudflare/clef"):
        assert structured.keys_of(model)
