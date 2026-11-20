"""AA's full public model catalogue, loaded like its web client from the page-data manifest.

Inline chart data is only a preview (~30 models). The manifest next to initialModels points to the full
catalogue; its public key authenticates AES-GCM bytes (nonce = SHA256(key)[:12]), then gzip JSON.
Never substitute the preview when the full catalogue fails to load.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from typing import Any, Iterator
from urllib.request import Request, urlopen

from walter_router.research.benchmarks.aa import ANCHORS, AA_MODEL_URL, flight_text
from walter_router.research.web import MAX_BYTES, fetch_text

AA_ORIGIN = "https://artificialanalysis.ai"
MIN_CATALOGUE = 300


def flight_values(page: str) -> Iterator[Any]:
    """JSON records of the complete flight stream, including records split across script pushes."""
    decoder = json.JSONDecoder()
    for line in flight_text(page).splitlines():
        pos = 0
        while pos < len(line):
            prefix = re.match(r"[0-9a-z]+:", line[pos:])
            if prefix:
                pos += prefix.end()
            try:
                value, pos = decoder.raw_decode(line, pos)
            except ValueError:
                break  # imports, text records and unresolved React references are not JSON records
            yield value


def objects(value: Any) -> Iterator[dict]:
    """Walk object/list trees without interpreting React reference strings as data."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def fetch_data(path: str) -> bytes:
    """Bounded binary read from AA's fixed origin; manifests cannot select another host or arbitrary path."""
    if not isinstance(path, str) or not re.fullmatch(r"/data/[A-Za-z0-9_-]+\.(?:txt|json)", path):
        raise ValueError("AA catalogue: invalid manifest path")
    req = Request(AA_ORIGIN + path, headers={"User-Agent": "Walter-Router/1.0", "Accept": "*/*"})
    with urlopen(req, timeout=60) as response:  # noqa: S310 (fixed origin, validated public data path)
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("AA catalogue: response too large")
    return raw


def manifest_data(manifest: dict) -> Any:
    """Decode and authenticate the public page-data format; malformed/incomplete data fails closed."""
    raw = fetch_data(manifest.get("path"))
    key = manifest.get("key")
    if key:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", key):
            raise ValueError("AA catalogue: invalid public manifest key")
        key_bytes = bytes.fromhex(key)
        raw = AESGCM(key_bytes).decrypt(hashlib.sha256(key_bytes).digest()[:12], raw, None)
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("AA catalogue: decoded data too large")
    return json.loads(raw)


def catalogue_models(page: str) -> list[dict]:
    """The model context's catalogue, excluding the separate host-endpoint manifest on the same page."""
    for value in flight_values(page):
        for obj in objects(value):
            preview = obj.get("initialModels")
            if not isinstance(preview, list) or not any(isinstance(m, dict) and m.get("slug") for m in preview):
                continue
            manifest = obj.get("manifest")
            if manifest is not None:
                if not isinstance(manifest, dict):
                    raise ValueError("AA catalogue: invalid manifest")
                data = manifest_data(manifest)
                models = data.get("models") if isinstance(data, dict) else data
            else:
                models = preview  # older full inline catalogue
            if not isinstance(models, list) or any(not isinstance(m, dict) or not m.get("slug") for m in models):
                raise ValueError("AA catalogue: models lack canonical AA slugs")
            if len({m["slug"] for m in models}) < MIN_CATALOGUE:
                raise ValueError(f"AA catalogue: only {len(models)} models (partial chart data)")
            return models
    raise ValueError("AA catalogue: no model context found")


def model_catalogue() -> tuple[list[dict], str]:
    """Read a current model page and its full catalogue; try other anchors if one is retired."""
    errors = []
    for anchor in ANCHORS:
        url = AA_MODEL_URL.format(anchor)
        try:
            return catalogue_models(fetch_text(url)), url
        except Exception as exc:  # noqa: BLE001 — another anchor may remain usable
            errors.append(f"{anchor}: {type(exc).__name__}: {exc}"[:180])
    raise ValueError("AA catalogue: " + "; ".join(errors))
