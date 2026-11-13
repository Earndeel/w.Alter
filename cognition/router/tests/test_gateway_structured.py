"""SOCLE A6 (2026-11-11): walter-llm executes typed decisions and rerank on the Router's chain, offline here."""
import ast
import asyncio
import hashlib
import json
import re
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
import structured  # noqa: E402


@pytest.fixture(autouse=True)
def _no_route_set_aside():
    structured._unavailable.clear()
    yield
    structured._unavailable.clear()


# ── fixtures ────────────────────────────────────────────────────────────────────────────────────────────────────
def old_merge(samples):
    """walter_memory.llm.merge_answers as it was before the move (2026-11-11), verbatim: the parity reference."""
    out = {}
    for k, first in samples[0].items():
        got = [s[k] for s in samples if isinstance(s.get(k), dict)]
        if first.get("type") == "noul":
            out[k] = {**first, "noul": sum(g.get("noul") or 0 for g in got) / len(got)}
            continue
        options = list(dict.fromkeys(o for g in got for o in (g.get("probabilities") or {})))
        if not options:
            out[k] = first
            continue
        p = {o: sum((g.get("probabilities") or {}).get(o, 0) for g in got) / len(got) for o in options}
        choice = max(options, key=lambda o: p[o])
        agree = [g for g in got if g.get("choice") == choice]
        out[k] = {**first, "choice": choice, "probabilities": p,
                  "confidence": sum(g.get("confidence") or 0 for g in agree) / len(got),
                  "agreement": len(agree) / len(got)}
    return out


SAMPLES = [
    {"cap": {"type": "noul", "noul": 0.37}, "task": {"choice": "a", "probabilities": {"a": 0.6, "b": 0.4}, "confidence": 0.6},
     "free": {"choice": "x"}},
    {"cap": {"type": "noul", "noul": 0.55}, "task": {"choice": "b", "probabilities": {"a": 0.45, "b": 0.55}, "confidence": 0.55},
     "free": {"choice": "y"}},
    {"cap": {"type": "noul", "noul": 0.49}, "task": {"choice": "a", "probabilities": {"a": 0.7, "b": 0.2, "c": 0.1},
                                                     "confidence": 0.7}, "free": {"choice": "x"}},
]


class Resp:
    def __init__(self, status, data):
        self.status_code, self.data = status, data

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class Client:
    """A fake httpx.AsyncClient: replies by URL substring, records every call (URL, headers, body)."""

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    async def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        for part, reply in self.replies.items():
            if part in url:
                out = reply(json) if callable(reply) else reply
                if isinstance(out, Exception):
                    raise out
                return Resp(*out)
        raise AssertionError(url)

    async def get(self, url, headers=None, timeout=None):
        return await self.post(url, headers=headers)


def key(name):
    return f"fixture-{name.lower()}"


def run(coro):
    return asyncio.run(coro)


Q = {"task": {"type": "choice", "criteria": {"a": "A", "b": "B"}}}


def answer(choice="a", cost=0.00007):
    return 200, {"model": "inception/mercury-decide-20261001", "usage": {"cost": cost, "prompt_tokens": 120},
                 "answers": {"task": {"choice": choice, "probabilities": {"a": 0.8, "b": 0.2}, "confidence": 0.8}}}


# ── merge ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [1, 2, 3])
def test_samples_merge_is_identical_to_the_former_memory_merge(n):
    assert structured.merge_answers(SAMPLES[:n]) == old_merge(SAMPLES[:n])
    merged = structured.merge_answers(SAMPLES)
    assert merged["task"]["choice"] == "a" and merged["task"]["agreement"] == pytest.approx(2 / 3)
    assert merged["cap"]["noul"] == pytest.approx((0.37 + 0.55 + 0.49) / 3)


# ── decisions ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_chain_falls_back_in_the_routers_order_and_reports_each_attempt():
    logs = []
    client = Client({"alpha/decisions": lambda body: (402, {"error": {"code": 402, "message": "credits; key sk-x"}})
                     if body["model"] == "liquid/d1-ultra" else answer(),
                     "cloudflare": (500, {})})
    code, out = run(structured.decisions({"state": {"m": "x"}, "questions": Q}, client=client, key=key, log=logs.append,
                                         chain=["liquid/d1-ultra", "inception/mercury-decide:free", "cloudflare/clef"]))
    assert code == 200 and out["answers"]["task"]["choice"] == "a"
    assert out["route"] == "openrouter/inception/mercury-decide:free"
    assert out["attempts"] == [{"provider": "openrouter", "model": "liquid/d1-ultra", "reason": "HTTP 402 402"}]
    assert [(c["model"], c["ok"]) for c in logs] == [("liquid/d1-ultra", False), ("inception/mercury-decide:free", True)]
    assert logs[1]["cost_usd"] == 0.00007 and logs[1]["cost_status"] == "reported"
    assert "sk-x" not in json.dumps(out) and "credits" not in json.dumps(out)       # provider text never echoed
    assert all(c["headers"]["Authorization"].startswith("Bearer fixture-") for c in client.calls)


def test_samples_are_parallel_calls_merged_with_the_authoritative_merge():
    answers = iter([s for s in SAMPLES])
    client = Client({"alpha/decisions": lambda body: (200, {"answers": next(answers), "usage": {"cost": 0.0}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q, "samples": 3}, client=client, key=key,
                                         log=lambda e: None, chain=["inception/mercury-decide:free"]))
    assert code == 200 and out["samples"] == 3 and len(client.calls) == 3 and len(out["calls"]) == 3
    assert out["answers"] == old_merge(SAMPLES)


def test_whole_chain_failure_is_explicit_and_lists_every_attempt_without_secrets():
    def missing(name):
        if name.startswith("CLOUDFLARE"):
            raise structured.MissingGrant("missing_grant: CLOUDFLARE_AI_TOKEN: llm is not allowed by cloudflare-workers-ai")
        return key(name)
    client = Client({"alpha/decisions": httpx.ConnectTimeout("t")})
    code, out = run(structured.decisions({"state": {}, "questions": Q}, client=client, key=missing, log=lambda e: None,
                                         chain=["inception/mercury-decide:free", "cloudflare/clef"]))
    assert code == 502 and out["error"] == "no decision model answered"
    assert [a["reason"] for a in out["attempts"]] == [
        "ConnectTimeout", "missing_grant: CLOUDFLARE_AI_TOKEN: llm is not allowed by cloudflare-workers-ai"]
    assert "fixture-" not in json.dumps(out)


def test_cloudflare_adapter_prices_input_tokens_and_keeps_the_model():
    client = Client({"cloudflare": (200, {"success": True, "result": {
        "answers": {"task": {"choice": "b"}}, "usage": {"input_tokens": 1000}}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q}, client=client, key=key, log=lambda e: None,
                                         chain=["cloudflare/clef"]))
    assert code == 200 and out["model"] == "cloudflare/clef" and out["provider"] == "cloudflare"
    assert out["calls"][0]["cost_usd"] == pytest.approx(0.24 * 1000 / 1e6)
    assert client.calls[0]["url"].endswith("/ai/run/@cf/cloudflare/clef")
    assert client.calls[0]["json"]["model"] == "clef"


def test_a_named_model_narrows_the_chain_and_an_unknown_one_is_refused():
    client = Client({"alpha/decisions": answer()})
    chain = ["liquid/d1-ultra", "inception/mercury-decide:free"]
    code, _ = run(structured.decisions({"state": {}, "questions": Q, "model": "inception/mercury-decide:free"},
                                       client=client, key=key, log=lambda e: None, chain=chain))
    assert code == 200 and [c["json"]["model"] for c in client.calls] == ["inception/mercury-decide:free"]
    code, out = run(structured.decisions({"state": {}, "questions": Q, "model": "evil/other"}, client=client, key=key,
                                         log=lambda e: None, chain=chain))
    assert code == 400 and "not offered" in out["error"] and len(client.calls) == 1


def test_paid_model_below_the_callers_floor_is_skipped_free_ones_still_answer():
    async def low():
        return 0.5
    client = Client({"alpha/decisions": answer()})
    code, out = run(structured.decisions({"state": {}, "questions": Q, "paid_floor_usd": 1.0}, client=client, key=key,
                                         log=lambda e: None, balance=low,
                                         chain=["liquid/d1-ultra", "inception/mercury-decide:free"]))
    assert code == 200 and out["attempts"][0]["reason"] == "balance_below_floor"
    assert [c["json"]["model"] for c in client.calls] == ["inception/mercury-decide:free"]


def test_a_late_sample_does_not_hold_the_decision():
    """13/11/2026: one sample in three took 9.6 s; the plan of the message waited for it and missed its caller."""
    class Slow(Client):
        async def post(self, url, headers=None, json=None, timeout=None):
            n = len(self.calls)
            out = await super().post(url, headers=headers, json=json, timeout=timeout)
            if n == 1:
                await asyncio.sleep(5)
            return out
    answers = iter(SAMPLES)
    logs = []
    client = Slow({"alpha/decisions": lambda body: (200, {"answers": next(answers), "usage": {"cost": 0.0}})})
    t0 = time.perf_counter()
    code, out = run(structured.decisions({"state": {}, "questions": Q, "samples": 3, "straggler_s": 0.2}, client=client,
                                         key=key, log=logs.append, chain=["inception/mercury-decide:free"]))
    assert time.perf_counter() - t0 < 2 and code == 200 and out["samples"] == 2
    assert out["answers"] == old_merge([SAMPLES[0], SAMPLES[2]])
    assert [c.get("skipped") for c in out["calls"]].count("straggler") == 1
    assert sum(1 for e in logs if e.get("skipped") == "straggler") == 1 and sum(1 for e in logs if e["ok"]) == 2
    # a lone sample that answered is not a majority: the others are waited for (up to their own timeout)
    answers = iter(SAMPLES)
    client = Slow({"alpha/decisions": lambda body: (200, {"answers": next(answers), "usage": {"cost": 0.0}})})
    code, out = run(structured.decisions({"state": {}, "questions": Q, "samples": 2, "straggler_s": 0.1}, client=client,
                                         key=key, log=lambda e: None, chain=["inception/mercury-decide:free"]))
    assert code == 200 and out["samples"] == 2


def test_a_route_that_cannot_answer_is_set_aside_not_asked_again_at_every_decision():
    """13/11/2026: credit empty, the free model gone at the provider (404) and no grant for the last route: every
    decision spent 4.4 s asking the two dead routes again before failing."""
    def missing(name):
        if name.startswith("CLOUDFLARE"):
            raise structured.MissingGrant("missing_grant: CLOUDFLARE_AI_TOKEN: llm is not allowed by cloudflare-workers-ai")
        return key(name)
    state = {"gone": True}
    client = Client({"alpha/decisions": lambda body: (404, {"error": {"code": 404}}) if state["gone"] else answer()})
    chain = ["inception/mercury-decide:free", "cloudflare/clef"]
    body = {"state": {}, "questions": Q, "samples": 3}
    logs = []
    code, out = run(structured.decisions(body, client=client, key=missing, log=logs.append, chain=chain))
    assert code == 502 and len(client.calls) == 3
    code, out = run(structured.decisions(body, client=client, key=missing, log=logs.append, chain=chain))
    assert code == 502 and len(client.calls) == 3                      # nothing asked again
    assert [c.get("skipped") for c in out["calls"]] == ["route_unavailable", "route_unavailable"]
    assert [a["reason"].split(":")[0] for a in out["attempts"]] == ["route_unavailable", "route_unavailable"]
    assert "HTTP 404" in out["attempts"][0]["reason"] and "missing_grant" in out["attempts"][1]["reason"]
    assert sum(1 for e in logs if e.get("skipped") == "route_unavailable") == 2
    # … for a while only: the route is asked again afterwards, and an answer clears it
    structured._unavailable.update({m: (time.monotonic() - 1, why) for m, (_, why) in structured._unavailable.items()})
    state["gone"] = False
    code, out = run(structured.decisions(body, client=client, key=missing, log=logs.append, chain=chain))
    assert code == 200 and out["samples"] == 3 and "inception/mercury-decide:free" not in structured._unavailable
    # a passing failure (timeout, 5xx, no credit) never sets a route aside
    structured._unavailable.clear()
    client = Client({"alpha/decisions": (503, {})})
    run(structured.decisions(body, client=client, key=key, log=lambda e: None, chain=["liquid/d1-ultra"]))
    assert not structured._unavailable


@pytest.mark.parametrize("body", [{"questions": Q}, {"state": {}, "questions": {}}, {"state": {}, "questions": Q, "samples": 9},
                                  {"state": {}, "questions": Q, "samples": True}])
def test_malformed_requests_are_refused_before_any_call(body):
    client = Client({})
    code, _ = run(structured.decisions(body, client=client, key=key, log=lambda e: None, chain=["m/x"]))
    assert code == 400 and not client.calls


# ── rerank ──────────────────────────────────────────────────────────────────────────────────────────────────────
ROUTES = [{"provider": "openrouter", "model": "cohere/rerank-5-fast"}, {"provider": "openrouter", "model": "cohere/rerank-4-fast"}]


def test_rerank_is_normalised_and_falls_back_on_the_posts_routes():
    logs = []

    def reply(body):
        if body["model"] == "cohere/rerank-5-fast":
            return 503, {}
        return 200, {"model": body["model"], "usage": {"cost": 0.00001, "total_tokens": 50},
                     "results": [{"index": 2, "relevance_score": 0.9, "document": {"text": "c"}},
                                 {"index": 0, "relevance_score": 0.5}, {"index": 9, "relevance_score": 0.1}]}
    client = Client({"/rerank": reply})
    code, out = run(structured.rerank({"query": "q", "documents": ["a", "b", "c"], "top_n": 2}, routes=ROUTES,
                                      client=client, key=key, log=logs.append))
    assert code == 200 and out["results"] == [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.5}]
    assert out["model"] == "cohere/rerank-4-fast" and out["attempts"] == [
        {"provider": "openrouter", "model": "cohere/rerank-5-fast", "reason": "HTTP 503"}]
    assert client.calls[0]["json"]["top_n"] == 2 and out["cost_usd"] == 0.00001
    assert [e["ok"] for e in logs] == [False, True]


def test_rerank_failure_is_explicit_and_a_model_off_the_poste_is_refused():
    client = Client({"/rerank": (500, {})})
    code, out = run(structured.rerank({"query": "q", "documents": ["a"]}, routes=ROUTES[:1], client=client, key=key,
                                      log=lambda e: None))
    assert code == 502 and out["attempts"][0]["reason"] == "HTTP 500"
    code, out = run(structured.rerank({"query": "q", "documents": ["a"], "model": "other/x"}, routes=ROUTES, client=client,
                                      key=key, log=lambda e: None))
    assert code == 400
    code, out = run(structured.rerank({"query": "q", "documents": ["a"]}, routes=[], client=client, key=key,
                                      log=lambda e: None))
    assert code == 503


# ── HTTP endpoints (gateway.build_app with fixture dependencies) ─────────────────────────────────────────────────
def app_ns(tmp_path, monkeypatch, chain=("inception/mercury-decide:free",)):
    source = LLM / "gateway.py"
    tree = ast.parse(source.read_text())
    names = {"build_app", "_correlation", "_channel", "_uuid", "_dsh_session", "log"}
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    agents = tmp_path / "agents.json"
    agents.write_text(json.dumps({hashlib.sha256(b"fixture-token").hexdigest(): {"agent": "walter-memory"}}))
    logs = []
    ns = {"json": json, "hashlib": hashlib, "uuid": uuid, "time": time, "re": re, "Request": Request,
          "threading": SimpleNamespace(Thread=lambda **k: SimpleNamespace(start=lambda: None)),
          "AGENTS": agents, "TEST_BUDGET": {"accounts": ["e2e"]}, "warm": lambda: None, "_install_codex_auth": lambda: None,
          "decision_chain": lambda: list(chain),
          "decision": lambda task: {"execution": ROUTES[:1]} if task == "rerank" else pytest.fail(task),
          "structured_key": key, "_run_metadata": lambda run: {"run_id": run, "status": "open",
                                                                "privacy_class": "cloud_allowed"}}
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace())

    async def inline(fn, *a, **k):
        return fn(*a, **k)
    monkeypatch.setattr(asyncio, "to_thread", inline)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    ns["log"] = logs.append
    return ns, logs


def post(app, path, body, headers=None):
    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
            return await client.post(path, json=body, headers={"Authorization": "Bearer fixture-token", **(headers or {})})
    return asyncio.run(call())


def test_decisions_endpoint_logs_task_decision_with_the_callers_run(tmp_path, monkeypatch):
    ns, logs = app_ns(tmp_path, monkeypatch)

    async def once(client, key, model, state, questions, timeout):
        return {"answers": {"task": {"choice": "a"}}, "usage": {}, "model": model, "cost_usd": 0.00007,
                "cost_status": "reported", "input_tokens": 10}
    monkeypatch.setattr(structured, "decide_once", once)
    run_id = "11111111-1111-4111-8111-111111111111"
    r = post(ns["build_app"](), "/v1/decisions", {"state": {}, "questions": Q, "samples": 2}, {"X-Walter-Run-Id": run_id})
    assert r.status_code == 200 and r.json()["samples"] == 2
    assert r.headers["x-walter-route"] == "openrouter/inception/mercury-decide:free"
    assert len(logs) == 2 and all(e["task"] == "decision" and e["kind"] == "decision" and e["run_id"] == run_id
                                  and e["agent"] == "walter-memory" and e["cost_usd"] == 0.00007 for e in logs)
    assert post(ns["build_app"](), "/v1/decisions", {"state": {}, "questions": Q},
                {"Authorization": "Bearer wrong"}).status_code == 401


def test_decisions_endpoint_failure_is_a_structured_502(tmp_path, monkeypatch):
    ns, logs = app_ns(tmp_path, monkeypatch, chain=("a/one", "b/two"))

    async def once(*a, **k):
        raise structured.ProviderError(429)
    monkeypatch.setattr(structured, "decide_once", once)
    r = post(ns["build_app"](), "/v1/decisions", {"state": {}, "questions": Q})
    body = r.json()["detail"] if "detail" in r.json() else r.json()
    assert r.status_code == 502
    assert [a["reason"] for a in body["error"]["attempts"]] == ["HTTP 429", "HTTP 429"]


def test_chain_unavailable_is_503_never_a_built_in_chain(tmp_path, monkeypatch):
    ns, _ = app_ns(tmp_path, monkeypatch)
    ns["decision_chain"] = lambda: (_ for _ in ()).throw(RuntimeError("walter-router down"))
    r = post(ns["build_app"](), "/v1/decisions", {"state": {}, "questions": Q})
    assert r.status_code == 503 and r.json()["error"]["message"] == "decision chain unavailable"


def test_rerank_endpoint_uses_the_rerank_poste(tmp_path, monkeypatch):
    ns, logs = app_ns(tmp_path, monkeypatch)

    async def once(client, key, model, query, documents, top_n, timeout):
        return {"results": [{"index": 1, "relevance_score": 0.7}, {"index": 0, "relevance_score": 0.2}], "usage": {},
                "model": model, "cost_usd": None, "cost_status": "unknown"}
    monkeypatch.setattr(structured, "rerank_once", once)
    r = post(ns["build_app"](), "/v1/rerank", {"query": "q", "documents": ["a", "b"]})
    assert r.status_code == 200 and [x["index"] for x in r.json()["results"]] == [1, 0]
    assert r.json()["model"] == "cohere/rerank-5-fast" and logs[0]["task"] == "rerank" and logs[0]["kind"] == "rerank"


def test_no_hardcoded_decision_chain_or_default_model_in_the_gateway():
    src = (LLM / "gateway.py").read_text() + (LLM / "structured.py").read_text()
    assert "mercury-decide" not in src and "rerank-4-fast" not in src and "rerank-5-fast" not in src
