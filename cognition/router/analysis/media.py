"""What a media offer actually sells: generation mode(s), output resolution, audio, and a comparable unit price.

Every provider labels its SKUs differently ("image-to-video", "Text /Image to Video", "Reference-to-Video Output",
"720p with video input", "Video (no audio)", "10.0s-1080p"...). This module turns one offer into:
  kind        generation | fee (input surcharge, web search) | tool (upscale, extend, lip sync, layers...)
  modes       t2i i2i t2v i2v r2v v2v — empty when the label does not say (generic generation SKU)
  resolution  480p / 720p / 1080p / 1K / 2K / 4K ...
  audio       True / False / None (unknown)
  norm_price  price in the interface unit (video: per second, image: per image), None if not convertible
"""
from __future__ import annotations

import re

NORM_UNITS = {"image": "per image", "video": "per second", "audio": "per 1000 characters", "music": None,
              "transcription": "per minute", "rerank": "per search", "embedding": "per 1m tokens"}
MODE_LABELS = {"t2i": "texte→image", "i2i": "image→image", "t2v": "texte→vidéo", "i2v": "image→vidéo",
               "r2v": "référence→vidéo", "v2v": "vidéo→vidéo"}

_FEE = re.compile(r"\b(image|font) input\b|reference image|web search|^input\b|\binput image\b", re.I)
_TOOL = re.compile(r"upscal|super resolution|\bextend\b|lip ?sync|speech to video|style creation|layer[- ]?decomposition"
                   r"|get (1080p|4k) video|avatar|avtar", re.I)
_NO_VIDEO_INPUT = re.compile(r"no video( input)?\b", re.I)
_V2V = re.compile(r"video[- ]to[- ]video|video[- ]?edit|videoedit|with video( input)?\b|(^|[,|] *)video input|motion control"
                  r"|animate (move|replace)", re.I)
_R2V = re.compile(r"reference[- ]to[- ]video|\br2v\b|reference[- ]to[- ]video output", re.I)
_I2V = re.compile(r"image[- ]to[- ]video|text */ *image to video|\bi2v\b", re.I)
_T2V = re.compile(r"text[- ]to[- ]video|text */ *image to video|\bt2v\b", re.I)
_I2I = re.compile(r"image[- ]to[- ]image|image edit|\bedit\b|reframe|kontext", re.I)
_T2I = re.compile(r"text[- ]to[- ]image", re.I)
_RESOLUTION = re.compile(r"(?<![\d.])(\d{3,4})p\b|(?<![\d.])(\d(?:\.\d)?)k\b", re.I)
_MUSIC_GEN = re.compile(r"generate music|song generation|^music\b|text to music", re.I)
_BARE_TIER = re.compile(r"^\s*(\d{3,4})\s*$")
_DURATION = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)s\b")


def resolution(text: str, tier_label: str = "") -> str | None:
    m = _BARE_TIER.match(tier_label or "")
    if m:
        return f"{m.group(1)}p"
    m = _RESOLUTION.search(text)
    if not m:
        return None
    return f"{m.group(1)}p" if m.group(1) else f"{m.group(2)}K".replace(".0K", "K")


def resolution_rank(res: str | None) -> float:
    """Sort key: 480p < 720p < 1080p ~ 1K < 2K < 4K."""
    if not res:
        return 0.0
    return float(res[:-1]) if res.endswith("p") else float(res[:-1]) * 1080


def audio(text: str) -> bool | None:
    t = text.lower()
    if re.search(r"without audio|no audio|\(no audio|（no audio", t):
        return False
    if re.search(r"with audio|with aiduo|\baudio\b", t):
        return True
    return None


def classify(interface: str, label: str, input_modalities: list[str] | None = None) -> dict:
    """Classify one offer. `label` is the provider's own SKU text (without the model id); `input_modalities`
    (OpenRouter architecture) fills the modes when the label is generic ("Video Output", "Image Output")."""
    text = label.strip()
    if interface == "music":  # Suno on Kie lists lyrics, stems, covers... next to the song itself
        kind = "generation" if not text or _MUSIC_GEN.search(text) else "tool"
        return {"kind": kind, "modes": [], "resolution": None, "audio": None}
    if interface not in ("image", "video"):
        return {"kind": "generation", "modes": [], "resolution": None, "audio": None}
    if _TOOL.search(text):
        kind = "tool"
    elif _FEE.search(text) and not _NO_VIDEO_INPUT.search(text):
        kind = "fee"
    else:
        kind = "generation"
    modes: list[str] = []
    if interface == "video" and kind == "generation":
        if _V2V.search(text) and not _NO_VIDEO_INPUT.search(text):
            modes = ["v2v"]
        else:
            modes = [m for m, rx in (("t2v", _T2V), ("i2v", _I2V), ("r2v", _R2V)) if rx.search(text)]
            if not modes and input_modalities:
                ins = set(input_modalities)
                editor = "video" in ins and "image" not in ins  # text + video in, video out: an editor
                modes = (["t2v"] if "text" in ins and not editor else []) + (["i2v"] if "image" in ins else []) \
                    + (["v2v"] if "video" in ins else [])
            elif not modes and _NO_VIDEO_INPUT.search(text):
                modes = ["t2v", "i2v"]  # SKU priced "no video input" against "with video input": text/image prompt
    elif interface == "image" and kind == "generation":
        modes = [m for m, rx in (("t2i", _T2I), ("i2i", _I2I)) if rx.search(text)]
        if not modes and input_modalities:
            modes = (["t2i"] if "text" in input_modalities else []) + (["i2i"] if "image" in input_modalities else [])
    return {"kind": kind, "modes": modes, "resolution": resolution(text), "audio": audio(text) if interface == "video" else None}


def norm_price(interface: str, unit_price: float | None, unit: str | None, label: str) -> tuple[float | None, str | None]:
    """Price in the interface's comparable unit; 'per video' with an explicit duration ('10s', '6.0s') -> per second.
    A zero price is a free auxiliary operation, not a generation price."""
    want = NORM_UNITS.get(interface)
    if not unit_price or unit_price <= 0:
        return None, None
    got = (unit or "").strip().lower()
    if want is None or got == want:
        return unit_price, got or None
    if want == "per minute" and got in ("per second", "per hour"):   # transcription: audio minutes
        return unit_price * 60 if got == "per second" else unit_price / 60, want
    if want == "per 1000 characters" and got in ("per character", "per utf-8 byte"):
        return unit_price * 1000, want  # UTF-8 bytes ~ characters (accents count double: slight underestimate)
    if want == "per second" and got in ("per video", "per vedio"):
        m = _DURATION.search(label)
        if m and float(m.group(1)) > 0:
            return unit_price / float(m.group(1)), "per second"
    return None, got or None


def compatible(offer_modes: list[str] | None, wanted: list[str] | None) -> bool:
    """A generation offer fits a task when it declares one of the task's modes; a generic SKU (no declared mode)
    fits every generation mode except editing an input video."""
    if not wanted:
        return True
    if not offer_modes:
        return "v2v" not in wanted
    return bool(set(offer_modes) & set(wanted))


def short_modes(modes: list[str]) -> str:
    order = ["t2i", "i2i", "t2v", "i2v", "r2v", "v2v"]
    return "/".join(m for m in order if m in modes)
