"""2026-11-20 (owner: « lock le stt sur microsoft/mai-transcribe-2 ») — a transcription-only model on the stt poste is
called through OpenRouter's /audio/transcriptions and answered in chat shape; 429 bursts are waited out."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "llm"))
import transcription  # noqa: E402

MSGS = [{"role": "user", "content": [{"type": "text", "text": "Transcris."},
                                     {"type": "input_audio", "input_audio": {"data": "QUJD", "format": "ogg"}}]}]


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


class _Client:
    def __init__(self, answers):
        self.answers, self.bodies = list(answers), []

    async def post(self, url, json=None, timeout=None, headers=None):
        assert url.endswith("/audio/transcriptions") and headers["Authorization"].startswith("Bearer ")
        self.bodies.append(json)
        return self.answers.pop(0)


def test_audio_part_is_found_and_sent_with_its_format(monkeypatch):
    monkeypatch.setattr(transcription, "RETRY_WAITS", (0.0,))
    c = _Client([_Resp(429, {"error": {"metadata": {"retry_after_seconds": 0}}}),
                 _Resp(200, {"text": "bonjour", "usage": {"seconds": 6, "cost": 0.0002}})])
    r = asyncio.run(transcription.completion("microsoft/mai-transcribe-2", "k", MSGS, client=c))
    assert r.choices[0].message.content == "bonjour" and r.usage.cost == 0.0002
    assert c.bodies[0] == {"model": "microsoft/mai-transcribe-2", "input_audio": {"data": "QUJD", "format": "ogg"}}
    assert len(c.bodies) == 2


def test_no_audio_or_stream_is_refused_without_a_call():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(transcription.completion("m", "k", [{"role": "user", "content": "hi"}], client=_Client([])))
    with pytest.raises(ValueError):
        asyncio.run(transcription.completion("m", "k", MSGS, stream=True, client=_Client([])))


def test_router_marks_a_transcription_only_model():
    from walter_router.serve import media_exec
    from walter_router.store import db
    with db.connect() as conn:
        if media_exec.openrouter_id(conn, "mai-transcribe-2") is None:
            return
        assert not media_exec.chat_capable(conn, "mai-transcribe-2")
        assert media_exec.chat_capable(conn, "gemini-3-1-flash-lite")


# 2026-11-23: MAI-Transcribe-2 refuses m4a/mp4, aac and webm on /audio/transcriptions (HTTP 400; ogg, mp3, wav, flac
# pass) — iPhone voice notes from Beeper (audio/mp4) failed every night since 20/11. Such audio is turned into mp3 first.
def _sine(tmp_path, ext, *args):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg absent")
    p = tmp_path / f"s.{ext}"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", *args, str(p)],
                   check=True)
    return p


def test_a_refused_format_is_sent_as_mp3(tmp_path):
    import base64
    m4a = _sine(tmp_path, "m4a", "-c:a", "aac")
    msgs = [{"role": "user", "content": [{"type": "input_audio", "input_audio": {
        "data": base64.b64encode(m4a.read_bytes()).decode(), "format": "mp4"}}]}]
    c = _Client([_Resp(200, {"text": "", "usage": {}})])
    asyncio.run(transcription.completion("microsoft/mai-transcribe-2", "k", msgs, client=c))
    sent = c.bodies[0]["input_audio"]
    assert sent["format"] == "mp3"
    assert base64.b64decode(sent["data"])[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")


def test_an_accepted_format_is_sent_untouched():
    c = _Client([_Resp(200, {"text": "x", "usage": {}})])
    asyncio.run(transcription.completion("m", "k", MSGS, client=c))
    assert c.bodies[0]["input_audio"] == {"data": "QUJD", "format": "ogg"}


def test_audio_that_cannot_be_converted_is_refused_without_a_call():
    import pytest
    msgs = [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": "QUJD", "format": "m4a"}}]}]
    with pytest.raises(ValueError, match="transcription_audio_unreadable"):
        asyncio.run(transcription.completion("m", "k", msgs, client=_Client([])))
