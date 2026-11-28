"""Shared helpers of the Liquid-native bench (17/11/2026): keys read in-process from the Walter Secrets grants (never
printed, never written: every output goes through `mask`), one timed POST per provider, synthetic assets."""
from __future__ import annotations

import base64
import io
import json
import math
import struct
import sys
import time
import wave

import httpx

sys.path.insert(0, "/walter/core/security/secrets")
from walter_secrets import grants  # noqa: E402

LIQUID_URL = "https://api.liquid.ai/decisions/v1/systemone"
OR_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
OR_EXTRACTIONS = "https://openrouter.ai/api/alpha/extractions"
_KEYS = {"liquid": ("LIQUID_API_KEY", "router"), "openrouter": ("OPENROUTER_API_KEY", "router")}
_cache: dict = {}


def key(provider: str) -> str:
    if provider not in _cache:
        name, reader = _KEYS[provider]
        _cache[provider] = grants.env_value(name, reader)
    return _cache[provider]


def mask(text: str) -> str:
    for p in _KEYS:
        try:
            k = key(p)
        except Exception:
            continue
        if k:
            text = text.replace(k, "[masked]")
    return text


def post(provider: str, url: str, body: dict, timeout: float = 60, client: httpx.Client | None = None) -> dict:
    """One timed call → {status, ms, data, headers (rate-limit only), error}. Never raises."""
    t = time.perf_counter()
    c = client or httpx
    try:
        r = c.post(url, headers={"Authorization": f"Bearer {key(provider)}"}, json=body, timeout=timeout)
        ms = round((time.perf_counter() - t) * 1000, 1)
        try:
            data = r.json()
        except ValueError:
            data = {"raw": mask(r.text[:300])}
        rl = {k: v for k, v in r.headers.items() if k.lower().startswith(("x-ratelimit", "retry-after"))}
        return {"status": r.status_code, "ms": ms, "data": json.loads(mask(json.dumps(data))), "rl": rl}
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "ms": round((time.perf_counter() - t) * 1000, 1), "data": None, "rl": {},
                "error": mask(f"{type(e).__name__}: {e}")[:200]}


def liquid(model: str, body: dict, **kw) -> dict:
    return post("liquid", LIQUID_URL, {"model": model, **body}, **kw)


def or_decide(model: str, body: dict, **kw) -> dict:
    return post("openrouter", OR_DECISIONS, {"model": f"liquid/{model}", **body}, **kw)


def or_extract(model: str, body: dict, **kw) -> dict:
    return post("openrouter", OR_EXTRACTIONS, {"model": f"liquid/{model}", **body}, **kw)


# ── synthetic assets ──────────────────────────────────────────────────────────────────────────────────────────
def squares_png(n: int = 3, size: int = 512, side: int = 80) -> tuple[str, list[dict]]:
    """White picture with `n` red squares at known places and one blue circle → (data URL, truth boxes in fractions)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    xs = [(40, 60), (230, 200), (380, 340)][:n]
    truth = []
    for x, y in xs:
        d.rectangle([x, y, x + side, y + side], fill=(220, 0, 0))
        truth.append({"top": y / size, "bottom": (y + side) / size, "left": x / size, "right": (x + side) / size})
    d.ellipse([60, 380, 140, 460], fill=(0, 0, 220))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), truth


def wav_data(kind: str = "tone", seconds: float = 1.0, rate: int = 16000) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        if kind == "tone":
            frames = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(n))
        else:
            frames = b"\x00\x00" * n
        w.writeframes(frames)
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    i = (len(s) - 1) * q
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return round(s[lo] + (s[hi] - s[lo]) * (i - lo), 1)
