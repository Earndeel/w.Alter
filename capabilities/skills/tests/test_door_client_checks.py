"""Write door refusals, client fallback ladder, curation checks, holdout split, ranker round-trip."""
import subprocess

import zlib

import numpy as np
import pytest

from walter_skills import client, door, evaluate, store
from walter_skills.curation import base

SKILL = """---
name: {name}
description: "Use when testing the walter-skills door with a well formed skill."
---

# Test

1. Run `walter-skills health`.
"""


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "skills" / "devops" / "existing-skill").mkdir(parents=True)
    (tmp_path / "skills" / "devops" / "existing-skill" / "SKILL.md").write_text(SKILL.format(name="existing-skill"))
    for k, v in {"ROOT": tmp_path, "SKILLS": tmp_path / "skills", "ARCHIVE": tmp_path / "archive",
                 "DRAFTS": tmp_path / "drafts"}.items():
        monkeypatch.setattr(store, k, v)
    return tmp_path


def test_door_refuses_bad_input(tmp_store):
    with pytest.raises(door.Refused):
        door.propose("Bad Name", SKILL.format(name="x"), "a reason long enough to pass")
    with pytest.raises(door.Refused):
        door.propose("no-frontmatter", "# nothing", "a reason long enough to pass")
    with pytest.raises(door.Refused):
        door.propose("leaky-skill", SKILL.format(name="leaky-skill") + "\nkey: sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD",
                     "a reason long enough to pass")
    with pytest.raises(door.Refused):
        door.propose("path-trick", SKILL.format(name="path-trick"), "a reason long enough to pass",
                     files={"../../etc/x": "no"})
    with pytest.raises(door.Refused):
        door.propose("existing-skill", SKILL.format(name="existing-skill"), "a reason long enough to pass")
    assert not (tmp_store / "drafts").exists() or not any((tmp_store / "drafts").iterdir())


def test_door_accepts_a_good_proposal_as_a_draft(tmp_store):
    r = door.propose("good-skill", SKILL.format(name="good-skill"), "captures a recurring test procedure")
    d = tmp_store / r["draft"]
    assert (d / "SKILL.md").exists() and store.read_sidecar(d)["kind"] == "new"


def test_client_falls_back_to_the_store_when_the_service_is_down(tmp_store, monkeypatch):
    monkeypatch.setattr(client, "URL", "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.setattr(client, "STORE", tmp_store)
    assert client.expose("message", "anything long enough here")["mode"] == "unavailable"
    rows = client.search("walter-skills door testing")
    assert rows and rows[0]["name"] == "existing-skill" and rows[0]["degraded"]
    assert "Run `walter-skills health`" in client.read("existing-skill")


def test_lossless_check_catches_a_lost_command():
    before = "Use `systemctl restart walter-skills` then curl http://127.0.0.1:8891/health"
    assert base.lossless(before, before, [])["ok"]
    assert not base.lossless(before, "Restart the service.", [])["ok"]
    assert base.lossless(before, "Restart.", [{"item": "systemctl restart walter-skills http://127.0.0.1:8891/health",
                                               "reason": "service retired"}])["ok"]


def test_sections_split_frontmatter_intro_and_headings():
    fm, intro, secs = base.sections("---\nname: x\n---\nintro\n## A\na\n## B\nb\n")
    assert fm.startswith("---") and intro.strip() == "intro" and [h for h, _ in secs] == ["## A", "## B"]


def test_holdout_is_deterministic_and_about_a_fifth():
    import hashlib
    ids = [hashlib.sha1(str(i).encode()).hexdigest()[:12] for i in range(2000)]
    share = sum(evaluate.is_holdout(q) for q in ids) / len(ids)
    assert 0.17 < share < 0.23 and all(evaluate.is_holdout(q) == evaluate.is_holdout(q) for q in ids[:50])


def test_ranker_trains_scores_and_round_trips():
    from walter_skills.ranker import Corpus, Ranker, score, features, train

    class Enc:
        model_name = "fake"

        def __call__(self, texts):
            # a hashed bag of words: deterministic (Python's hash() is salted per process and made this test flip)
            # and, like a real encoder, texts sharing words are close
            v = np.full((len(texts), 64), 0.01, dtype=np.float32)
            for row, t in enumerate(texts):
                for w in t.lower().replace("-", " ").split():
                    v[row, zlib.crc32(w.encode()) % 64] += 1
            return v / np.linalg.norm(v, axis=1, keepdims=True)

        def cached(self, texts, tag):
            return self(texts)

    skills = [{"name": n, "description": f"Use when {n.replace('-', ' ')}"} for n in
              ("beeper-messages", "kie-video", "telegram-debug", "cloudflare-deploy")]
    c = Corpus(skills, {}, Enc())
    ex = [{"query": q, "ctx": "", "ts": 0.0, "id": str(i), "labels": {g: (2, 1.0)}} for i, (q, g) in enumerate(
        [("lis mes messages beeper", "beeper-messages"), ("génère une vidéo kie", "kie-video"),
         ("le bot telegram plante", "telegram-debug"), ("déploie sur cloudflare", "cloudflare-deploy")] * 3)]
    r = train(c, [], ex, "fake", negatives=3)
    s = score(r, features(c, r, "messages beeper de sophie"))
    assert c.names[int(np.argmax(s))] == "beeper-messages"
    assert Ranker.loads(r.dumps()).weights == r.weights


def test_bundle_never_truncates_silently(tmp_path):
    d = tmp_path / "big-skill"
    (d / "references").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: big-skill\ndescription: Use when x\n---\nbody\n")
    (d / "references" / "long.md").write_text("x" * 50000 + "END-OF-FILE")
    s = store._load(d, "active", "")
    shown = base.bundle(s, per_file=40000)
    assert "END-OF-FILE" not in shown and "display truncated" in shown and "the file is complete on disk" in shown
    assert "END-OF-FILE" in base.bundle(s, per_file=60000)


def test_bus_consumer_routes_events(monkeypatch):
    """skill.changed from Hermes → sync of exactly those skills; drafts judged once per batch; learning splits
    turn.ended (implicit only) from session.ended (implicit + learner)."""
    from datetime import datetime, timedelta, timezone
    from walter_skills import consumer
    calls = {}
    monkeypatch.setattr(consumer.hermes_sync, "sync", lambda names: calls.setdefault("sync", names) and {})
    monkeypatch.setattr(consumer.curation, "run", lambda **kw: calls.setdefault("drafts", []).append(kw) or
                        {"summary": {"done": 0}})
    monkeypatch.setattr(consumer.cards, "refresh", lambda skills: 0)
    monkeypatch.setattr(consumer.store, "iter_skills", lambda: [])
    monkeypatch.setattr(consumer.jobs, "catalog", lambda: 0)
    monkeypatch.setattr(consumer.registry, "ledger", lambda *a, **k: None)
    monkeypatch.setattr(consumer.learning, "implicit", lambda session_ids: calls.setdefault("implicit", session_ids)
                        and {"implicit": 1})
    monkeypatch.setattr(consumer.learning, "drafts_from_sessions",
                        lambda session_ids, max_sessions: calls.setdefault("learner", session_ids) and {})
    ev = lambda i, t, src, sub: {"id": i, "type": t, "source": src, "subject": sub,  # noqa: E731
                                 "at": datetime.now(timezone.utc) - timedelta(minutes=5), "payload": {}}
    consumer.react([ev(1, "skill.changed", "hermes", "a"), ev(2, "skill.changed", "hermes", "b"),
                    ev(3, "skill.proposed", "claude_code", "c")])
    assert calls["sync"] == {"a", "b"} and len(calls["drafts"]) == 1
    consumer.learn([ev(4, "turn.ended", "dsh", "dsh/vm/s1"), ev(5, "session.ended", "hermes", "hermes/main/s2")])
    assert calls["implicit"] == ["dsh/vm/s1", "hermes/main/s2"] and calls["learner"] == ["hermes/main/s2"]



def test_hook_adapter_only_sends_failed_commands_and_cleans_dsh_prompts():
    """Regressions found on 2026-10-10: a SUCCESSFUL command printing 'Traceback' was treated as an error; dsh glues
    the contexts our hook injected into the next prompt (the domain map drowned the user's message)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("walter_hook", "/opt/walter-core/hooks/walter_hook.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    ok = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_response": {"stdout": "Traceback (most recent", "stderr": ""}}
    assert h.failed_output(ok) == ""
    assert h.failed_output({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "error": "Exit code 1\nboom"})
    assert h.failed_output({"hook_event_name": "PostToolUse", "tool_name": "bash", "tool_response": "out\n[exit code: 2]"})
    assert h.failed_output({"hook_event_name": "PostToolUse", "tool_name": "bash", "tool_response": "fine"}) == ""
    glued = h.ours("dsh", "Bibliothèque de skills…") + "Pourquoi Beeper renvoie 404 ?" + h.ours("dsh", "La commande a échoué")
    assert h.OWN.sub(" ", glued).strip() == "Pourquoi Beeper renvoie 404 ?"
    assert h.ours("claude_code", "x") == "x" and h.ours("dsh", "") == ""
