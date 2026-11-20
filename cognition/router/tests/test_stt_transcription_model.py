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
