"""Transcription-only models behind the chat door (owner 2026-11-20: STT poste = MAI-Transcribe-2).

The modules ask the `stt` poste the way they always did — chat/completions with one `input_audio` part — so the poste
can hold a chat model that hears audio (Gemini Flash-Lite) or a dedicated transcription model. The latter refuses
chat/completions on OpenRouter (HTTP 400 « is a transcription model »): this turns the same request into OpenRouter's
/audio/transcriptions call and answers in chat shape (the transcript as the assistant message, the vendor's cost in
`usage.cost`). The Router marks such a route `endpoint: "transcriptions"`.
"""
from __future__ import annotations

import time
import uuid

OPENROUTER_TRANSCRIPTIONS = "https://openrouter.ai/api/v1/audio/transcriptions"
RETRY_WAITS = (1.5, 3.0, 4.0)
# formats the endpoint takes for MAI-Transcribe-2, checked 2026-11-23: ogg, mp3, wav, flac pass; m4a/mp4, aac and webm
# answer HTTP 400 (iPhone voice notes from Beeper are audio/mp4: they failed every night since 20/11). Any other format
# is turned into mp3 by ffmpeg first, from a file (an mp4 with its index at the end cannot be read from a pipe).
ACCEPTED_FORMATS = {"ogg", "mp3", "wav", "flac"}
CONVERT_TIMEOUT_S = 120


async def accepted_audio(audio: dict) -> dict:
    """{data, format} the endpoint takes: as given when its format is accepted, else converted to mono mp3."""
    fmt = (audio.get("format") or "mp3").lower()
    if fmt in ACCEPTED_FORMATS:
        return {"data": audio["data"], "format": fmt}
    import asyncio
    import base64
    import binascii
    import tempfile
    from pathlib import Path
    try:
        raw = base64.b64decode(audio["data"], validate=False)
    except (binascii.Error, ValueError):
        raise ValueError(f"transcription_audio_unreadable:{fmt}") from None
    with tempfile.TemporaryDirectory(prefix="walter-stt-") as d:
        src, dst = Path(d) / "in.audio", Path(d) / "out.mp3"
        src.write_bytes(raw)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "48k", str(dst), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), timeout=CONVERT_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            raise ValueError(f"transcription_audio_unreadable:{fmt}") from None
        if proc.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
            raise ValueError(f"transcription_audio_unreadable:{fmt}")
        return {"data": base64.b64encode(dst.read_bytes()).decode("ascii"), "format": "mp3"}


def audio_part(messages: list[dict]) -> dict | None:
    """The last `input_audio` part of the request ({data, format}), or None."""
    found = None
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "input_audio" and part.get("input_audio"):
                    found = part["input_audio"]
    return found


def chat_shape(model: str, text: str, cost: float | None, seconds: float | None):
    import litellm
    usage = litellm.Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    if cost is not None:
        usage.cost = cost
    if seconds is not None:
        usage.audio_seconds = seconds
    return litellm.ModelResponse(id=f"walter-stt-{uuid.uuid4().hex[:12]}", created=int(time.time()), model=model,
                                 object="chat.completion", usage=usage,
                                 choices=[litellm.Choices(index=0, finish_reason="stop",
                                                          message=litellm.Message(role="assistant", content=text))])


async def completion(model: str, api_key: str, messages: list[dict], *, stream: bool = False,
                     timeout: float = 180, language: str | None = None, client=None):
    if stream:
        raise ValueError("transcription_model_no_stream")
    audio = audio_part(messages)
    if not audio or not audio.get("data"):
        raise ValueError("transcription_model_needs_input_audio")
    import httpx
    body = {"model": model, "input_audio": await accepted_audio(audio)}
    if language:
        body["language"] = language
    import asyncio
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    try:
        # the host answers short 429 bursts (« retry_after_seconds: 1 », seen 2026-11-20): wait them out briefly
        for wait in (*RETRY_WAITS, None):
            r = await client.post(OPENROUTER_TRANSCRIPTIONS, json=body, timeout=timeout,
                                  headers={"Authorization": f"Bearer {api_key}"})
            if r.status_code != 429 or wait is None:
                break
            try:
                after = float(((r.json().get("error") or {}).get("metadata") or {}).get("retry_after_seconds") or wait)
            except ValueError:
                after = wait
            await asyncio.sleep(min(max(after, wait), 5))
    finally:
        if own:
            await client.aclose()
    if r.status_code >= 400:
        raise RuntimeError(f"transcriptions HTTP {r.status_code}")
    d = r.json()
    usage = d.get("usage") or {}
    return chat_shape(model, d.get("text") or "", usage.get("cost"), usage.get("seconds"))
