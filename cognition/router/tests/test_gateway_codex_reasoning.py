"""20/11/2026: the route's reasoning effort reaches the Codex backend (litellm's ChatGPT transport dropped it silently).
Offline: the request is captured on a local stub, nothing leaves the machine."""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

LLM = Path(__file__).resolve().parents[1] / "llm"
sys.path.insert(0, str(LLM))
GATEWAY = (LLM / "gateway.py").read_text()


@pytest.fixture
def stub(monkeypatch):
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            seen.append(json.loads(self.rfile.read(n) or b"{}"))
            self.send_response(500); self.end_headers(); self.wfile.write(b'{"error":"stub"}')

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from litellm.llms.chatgpt import authenticator as A
    monkeypatch.setattr(A.Authenticator, "get_api_base", lambda self: f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(A.Authenticator, "get_access_token", lambda self: "stub")
    monkeypatch.setattr(A.Authenticator, "get_account_id", lambda self: "stub")
    yield seen
    srv.shutdown()


def _send(kwargs):
    import litellm
    litellm.drop_params = True
    try:
        asyncio.run(litellm.acompletion(model="chatgpt/gpt-6.1-sol", messages=[{"role": "user", "content": "x"}],
                                        stream=False, num_retries=0, timeout=5, **kwargs))
    except Exception:  # noqa: BLE001 — the stub answers 500: only the request matters
        pass


def test_the_codex_route_sends_its_reasoning_effort_and_without_the_rule_it_was_lost(stub):
    _send({"reasoning_effort": "xhigh"})                                      # what the gateway sent before 20/11
    assert stub and "reasoning" not in stub[-1] and "reasoning_effort" not in stub[-1]
    _send({"reasoning_effort": "xhigh", "allowed_openai_params": ["reasoning_effort"]})
    sent = stub[-1]
    assert sent.get("reasoning") == {"effort": "xhigh"} or sent.get("reasoning_effort") == "xhigh"


def test_both_gateway_paths_allow_the_effort_on_codex_only():
    assert GATEWAY.count('kwargs["allowed_openai_params"] = ["reasoning_effort"]') == 2
    assert GATEWAY.count('== "codex" and kwargs.get("reasoning_effort")') == 2
