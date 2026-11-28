"""Router `transcribe` (2026-11-11): audio file -> stt poste via walter-llm; refusals happen before any call."""
import json

from walter_router.serve import oneshot


def test_unsupported_format_is_refused_without_a_call(tmp_path, monkeypatch):
    f = tmp_path / "note.txt"
    f.write_text("x")
    monkeypatch.setattr(oneshot.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    r = oneshot.transcribe(str(f))
    assert r["ok"] is False and "unsupported" in r["error"]


def test_missing_file_and_missing_token(tmp_path, monkeypatch):
    assert oneshot.transcribe(str(tmp_path / "absent.ogg"))["error"] == "file not found"
    f = tmp_path / "a.ogg"
    f.write_bytes(b"OggS")
    monkeypatch.setattr(oneshot, "_llm_token", lambda: None)
    assert oneshot.transcribe(str(f))["error"].startswith("no walter-llm token")


def test_sends_input_audio_to_the_stt_poste(tmp_path, monkeypatch):
    f = tmp_path / "a.opus"
    f.write_bytes(b"OggS")
    seen = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"choices": [{"message": {"content": " bonjour "}}]}).encode()

    def fake(req, timeout):
        seen["body"] = json.loads(req.data)
        return R()

    monkeypatch.setattr(oneshot, "_llm_token", lambda: "t")
    monkeypatch.setattr(oneshot.urllib.request, "urlopen", fake)
    r = oneshot.transcribe(str(f), "test")
    assert r == {"file": str(f), "ok": True, "text": "bonjour"}
    assert seen["body"]["model"] == "stt"
    part = seen["body"]["messages"][0]["content"][0]
    assert part["type"] == "input_audio" and part["input_audio"]["format"] == "ogg"
