"""DSH steps glue runtime notices to the owner's message; only the owner's text may reach runs, memory and skills."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = 'The approval policy changed from "ask" to "never" (changed by the user).'


@pytest.fixture
def hook(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("walter_hook_dsh_owner", ROOT / "hooks" / "walter_hook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "DSH_OWNER_DIR", tmp_path)
    return mod


def record(tmp_path, sid, messages):
    """Run the real DSH adapter (owner-turn.mjs) on synthetic step messages."""
    if not shutil.which("node"):
        pytest.skip("node not installed")
    js = (f"import {{ record }} from {json.dumps(str(ROOT / 'hooks' / 'dsh' / 'owner-turn.mjs'))};"
          f"record({json.dumps(sid)}, {json.dumps(messages)}, {json.dumps(str(tmp_path))});")
    subprocess.run(["node", "--input-type=module", "-e", js], check=True)


def msg(kind, text):
    return {"role": "user", "source": {"kind": kind}, "content": [{"type": "text", "text": text}]}


def test_runtime_notice_is_not_owner_text(hook, tmp_path):
    record(tmp_path, "session-1", [msg("user-approval", NOTICE), msg("user", "test")])
    assert hook.dsh_owner_prompt("session-1", NOTICE + "test") == "test"


def test_step_without_owner_message_has_no_prompt(hook, tmp_path):
    record(tmp_path, "session-2", [msg("user-approval", NOTICE)])
    assert hook.dsh_owner_prompt("session-2", NOTICE) == ""


def test_missing_or_mismatched_record_keeps_the_glued_prompt(hook, tmp_path):
    assert hook.dsh_owner_prompt("absent", "hello") is None
    record(tmp_path, "session-3", [msg("user", "an older message")])
    assert hook.dsh_owner_prompt("session-3", "a different step") is None


def test_stale_record_is_ignored(hook, tmp_path):
    (tmp_path / "session-4.json").write_text(json.dumps({"at": 0, "owner": ["test"], "kinds": ["user"]}))
    assert hook.dsh_owner_prompt("session-4", "test") is None


def test_prompt_submit_skips_notice_only_step(hook, tmp_path, monkeypatch):
    record(tmp_path, "session-5", [msg("user-approval", NOTICE)])
    monkeypatch.setattr(hook, "runtime_of", lambda ev: "dsh")
    started = []
    monkeypatch.setattr(hook, "run_start", lambda *a, **k: started.append(a))
    out = hook.claude_code({"hook_event_name": "UserPromptSubmit", "session_id": "session-5", "prompt": NOTICE})
    assert out is None and started == []
