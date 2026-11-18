"""The images and voice notes of an owner message, for the preflight's decision model to read itself (18/11).

A door that receives a photo or a voice note keeps the file and says where in the message (Telegram:
« [photo reçue sur Telegram, enregistré ici : <path>] », « [note vocale de Telegram, transcrite ;
audio : <path>] <transcript> »); a caller may also pass `attachments` [{type, path}]. Only files under the
configured roots ([media] roots, `@instance/…` resolved), of a known image or audio type and under the size limits
are read; anything else is left out and said in the trace, never guessed. The transcript stays: the main model reads
text; the decision model reads the audio beside it when [media].audio is on (Liquid's own API reads OGG, MP3, WAV,
FLAC natively, measured 17/11)."""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

from .config import media_settings

IMAGE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
AUDIO = {".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
         ".flac": "audio/flac", ".m4a": "audio/mp4"}
# « …enregistré ici : <path>] » and « …; audio : <path>] »: the doors' markers
MARKER = re.compile(r"(?:enregistré ici|audio)\s*:\s*(/[^\]\s]+)")
MAX_ITEMS = 4


_INSTANCE: list = []


def _instance() -> str | None:
    """The instance root (`walter instance path`, once per process)."""
    if not _INSTANCE:
        import subprocess
        try:
            _INSTANCE.append(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True,
                                            timeout=10).stdout.strip() or None)
        except (OSError, subprocess.TimeoutExpired):
            return None
    return _INSTANCE[0]


def _roots(st: dict) -> list[Path]:
    out = []
    for r in st["roots"]:
        if r.startswith("@instance/"):
            base = _instance()
            if not base:                    # no instance: that root is not readable
                continue
            r = str(Path(base) / r[len("@instance/"):])
        out.append(Path(r).resolve())
    return out


def found(message: str, given: list | None = None) -> list[dict]:
    """[{type, path}] named by the message's markers and the caller's `attachments` (deduplicated, in order)."""
    out, seen = [], set()
    for m in given or []:
        if isinstance(m, dict) and isinstance(m.get("path"), str) and m["path"] not in seen:
            seen.add(m["path"])
            out.append({"type": m.get("type"), "path": m["path"]})
    for p in MARKER.findall(message or ""):
        if p not in seen:
            seen.add(p)
            out.append({"type": None, "path": p})
    return out


def load(message: str, given: list | None = None) -> tuple[list[dict], list[str]]:
    """→ (media for Walter Decision [{type, data: data URL}], notes on what was left out)."""
    st = media_settings()
    if not st["enabled"]:
        return [], []
    roots = _roots(st)
    media, notes = [], []
    for m in found(message, given)[:MAX_ITEMS]:
        p = Path(m["path"])
        ext = p.suffix.lower()
        kind = "image" if ext in IMAGE else "audio" if ext in AUDIO else None
        if kind is None:
            notes.append(f"{p.name}: not an image or audio file")
            continue
        if kind == "audio" and not st["audio"]:
            continue
        try:
            rp = p.resolve(strict=True)
        except OSError:
            notes.append(f"{p.name}: not found")
            continue
        if not any(rp.is_relative_to(r) for r in roots):
            notes.append(f"{p.name}: outside the readable roots")
            continue
        size = rp.stat().st_size
        limit = st["image_max_bytes"] if kind == "image" else st["audio_max_bytes"]
        if size > limit:
            notes.append(f"{p.name}: {size} bytes, over {limit}")
            continue
        mime = (IMAGE if kind == "image" else AUDIO).get(ext) or mimetypes.guess_type(rp.name)[0]
        media.append({"type": kind, "data": f"data:{mime};base64," + base64.b64encode(rp.read_bytes()).decode()})
    return media, notes
