"""What each model can do (models.model_details), from catalogues the cycle already reads — no extra call, nothing
billed (owner 2026-11-22: « les inputs qu'ils prennent, combien de tokens maximal… »).

Sources: the OpenRouter models list (context, max output, modalities, parameters, reasoning efforts, knowledge
cutoff, expiry) and the Codex account catalogue (context window, input modalities, reasoning levels). Ids are the
canonical ones through the offers of the same snapshot. The widest value wins; `sources` says who said what."""
from __future__ import annotations

import json

from walter_router.analysis import select as sel

LISTS = ("input_modalities", "output_modalities", "parameters", "reasoning_efforts")
NUMBERS = ("context_length", "max_output_tokens")
TEXTS = ("reasoning_default", "knowledge_cutoff", "expires")


def _openrouter(m: dict) -> dict:
    arch, top, rs = m.get("architecture") or {}, m.get("top_provider") or {}, m.get("reasoning") or {}
    return {"context_length": top.get("context_length") or m.get("context_length"),
            "max_output_tokens": top.get("max_completion_tokens"),
            "input_modalities": arch.get("input_modalities"), "output_modalities": arch.get("output_modalities"),
            "parameters": m.get("supported_parameters"),
            "reasoning_efforts": rs.get("supported_efforts"), "reasoning_default": rs.get("default_effort"),
            "knowledge_cutoff": m.get("knowledge_cutoff"), "expires": m.get("expiration_date")}


def _ids(conn, sid: int, provider: str) -> dict[str, str]:
    return {r["offer_key"]: r["model_id"] for r in conn.execute(
        "select distinct offer_key, model_id from models.offers where snapshot_id = %s and provider = %s", (sid, provider))}


def collect(conn) -> dict[str, dict]:
    snaps = sel.latest_snapshots(conn)
    found: list[tuple[str, str, dict]] = []      # (model_id, source, fields)
    for kind, provider, read in (("openrouter", "openrouter", lambda raw: {m.get("id"): _openrouter(m)
                                                                          for m in raw.get("data") or []}),
                                 ("codex", "codex", lambda raw: raw.get("details") or {})):
        sid = snaps.get(kind)
        if not sid:
            continue
        raw = conn.execute("select raw from models.snapshots where snapshot_id = %s", (sid,)).fetchone()["raw"]
        ids = _ids(conn, sid, provider)
        for key, fields in read(raw).items():
            if ids.get(key):
                found.append((ids[key], kind, fields))
    out: dict[str, dict] = {}
    for mid, src, f in found:
        d = out.setdefault(mid, {"sources": {}})
        for k in NUMBERS:
            v = f.get(k)
            if isinstance(v, (int, float)) and v > 0 and v >= (d.get(k) or 0):
                d[k] = int(v)
                d["sources"].setdefault(k, []).append(src)
        for k in LISTS:
            v = [x for x in f.get(k) or [] if isinstance(x, str)]
            if v:
                d[k] = sorted(set(d.get(k) or []) | set(v))
                d["sources"].setdefault(k, []).append(src)
        for k in TEXTS:
            if f.get(k) and not d.get(k):
                d[k] = str(f[k])
                d["sources"].setdefault(k, []).append(src)
    return out


def refresh(conn) -> int:
    rows = collect(conn)
    if not rows:                     # a source down keeps the previous details
        return 0
    cols = NUMBERS + LISTS + TEXTS
    conn.execute("delete from models.model_details")
    for mid, d in rows.items():
        conn.execute(f"""insert into models.model_details (model_id, {", ".join(cols)}, sources)
                         values (%s, {", ".join(["%s"] * len(cols))}, %s)""",
                     (mid, *[d.get(c) for c in cols], json.dumps({k: sorted(set(v)) for k, v in d["sources"].items()})))
    return len(rows)
