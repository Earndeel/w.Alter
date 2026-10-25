"""walter_hook: the walter-context preflight in shadow mode (detached, records only, never delays the prompt)."""
import importlib.util
import json
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "walter_hook.py"


@pytest.fixture
def hook(monkeypatch):
    spec = importlib.util.spec_from_file_location("walter_hook_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sent = []

    class FakePopen:
        def __init__(self, cmd, **kw):
            self.cmd, self.kw = cmd, kw
            self.stdin = self

        def write(self, data):
            sent.append((self.cmd, self.kw, json.loads(data)))

        def close(self):
            pass
    monkeypatch.setattr(mod.subprocess, "Popen", FakePopen)
    return mod, sent


def test_shadow_request_is_detached_and_carries_the_previous_exchange(hook, tmp_path):
    mod, sent = hook
    t = tmp_path / "s.jsonl"
    t.write_text("{}\n" + json.dumps({"type": "user", "timestamp": "2026-10-25T10:00:00Z",
                                       "message": {"content": "Je lance le lot B ?"}}) + "\n" +
                 json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Oui, en fantôme."}]}}))
    mod.preflight_shadow("On mesure le preflight sur les vrais messages", "claude_code", "abc", str(t))
    cmd, kw, req = sent[0]
    assert cmd == ["walter-context-preflight", "--shadow"] and kw["start_new_session"]
    assert req["default_thread"] == "session:abc" and req["previous"]["thread_id"] == "session:abc"
    assert req["previous"]["message"] == "Je lance le lot B ?" and req["previous"]["answer"] == "Oui, en fantôme."
    assert req["privacy_class"] == "cloud_allowed" and req["previous"]["age_s"] > 0


def test_secrets_stay_local_and_switches_hold(hook, monkeypatch):
    mod, sent = hook
    mod.preflight_shadow("voici la clé sk-or-v1-" + "a" * 48 + " pour le test", "claude_code", "abc", None)
    assert sent[-1][2]["privacy_class"] == "local_only"
    n = len(sent)
    mod.preflight_shadow("une question normale pour la suite", "dsh", "abc", None)       # dsh reaps detached children
    mod.preflight_shadow("<task-notification> done", "claude_code", "abc", None)       # machine prompt
    monkeypatch.setenv("WALTER_HOOK_PREFLIGHT", "off")
    mod.preflight_shadow("une question normale pour la suite", "claude_code", "abc", None)
    assert len(sent) == n
