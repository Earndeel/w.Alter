"""Writes a snapshot and its parsed rows, with identities (models.canonical / aliases)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from walter_router.analysis import identity
from walter_router.analysis.parse import OFFER_KINDS, parse_benchmarks, parse_offers

NAME_PRIORITY = {"openrouter": 1, "hermes_providers": 2, "aa": 3, "mm": 4, "bridgebench": 5, "arena": 6, "kie": 7, "da": 8,
                 "aa_stt": 9, "agentset": 10, "mteb": 11}


def _display_name(namespace: str, name: str | None) -> str | None:
    if not name or namespace not in NAME_PRIORITY:
        return None
    if namespace in ("aa", "mm", "arena", "aa_stt"):
        name = re.sub(r"\s*\([^)]*\)", "", name).strip()  # effort tier / 'based on' notes are variants, not names
    return name if namespace != "kie" else name.split(",")[0].strip()


def _apply_meta(conn, namespace: str, model_id: str, meta: dict | None) -> None:
    """Open weights / licence: 'open' from any source wins (Arena licence, AA open_weights, a Hugging Face id);
    'proprietary' only fills an unknown. The Arena licence text is preferred."""
    if meta and meta.get("context_length"):
        conn.execute("""update models.canonical set context_length = greatest(coalesce(context_length, 0), %s)
                        where model_id = %s""", (int(meta["context_length"]), model_id))
    if not meta or meta.get("open_weights") is None:
        return
    conn.execute("""update models.canonical set
                      open_weights = case when %(ow)s then true else coalesce(open_weights, false) end,
                      license = case when %(lic)s::text is not null and (license is null or %(src)s = 'arena')
                                     then %(lic)s else license end,
                      license_source = case when %(lic)s::text is not null and (license is null or %(src)s = 'arena')
                                            then %(src)s else coalesce(license_source, %(src)s) end
                    where model_id = %(id)s""",
                 {"ow": meta["open_weights"], "lic": meta.get("license") or (f'hf:{meta["hf"]}' if meta.get("hf") else None),
                  "src": namespace, "id": model_id})


def _ensure_identity(conn, namespace: str, key: str, model_id: str, vendor: str | None = None,
                     name: str | None = None) -> None:
    content_policy, base = identity.policy(model_id)
    conn.execute("""insert into models.canonical (model_id, vendor, content_policy, base_model_id) values (%s, %s, %s, %s)
                    on conflict (model_id) do update set content_policy = excluded.content_policy,
                      base_model_id = excluded.base_model_id
                    where models.canonical.content_policy is distinct from excluded.content_policy
                       or models.canonical.base_model_id is distinct from excluded.base_model_id""",
                 (model_id, vendor, content_policy, base))
    name = _display_name(namespace, name)
    if name:  # the most readable source names the model (OpenRouter > AA > AA multimodal > Arena > Kie > Design Arena)
        conn.execute("""update models.canonical set display_name = %s, display_source = %s where model_id = %s
                        and (display_source is null or display_source = %s
                             or coalesce((%s::jsonb ->> display_source)::int, 99) > %s)""",
                     (name, namespace, model_id, namespace, json.dumps(NAME_PRIORITY), NAME_PRIORITY[namespace]))
    origin = "manual" if key in identity.MANUAL.get(namespace, {}) else "auto"
    conn.execute("""insert into models.aliases (namespace, external_key, model_id, origin) values (%s, %s, %s, %s)
                    on conflict (namespace, external_key) do update set model_id = excluded.model_id, origin = excluded.origin
                    where models.aliases.origin = 'auto' or excluded.origin = 'manual'""",
                 (namespace, key, model_id, origin))


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _insert_endpoints(conn, sid: int, doc: dict) -> int:
    """Hosts behind OpenRouter (research.prices.openrouter_endpoints) -> models.endpoints, prices in $/M tokens."""
    conn.execute("delete from models.endpoints where snapshot_id = %s", (sid,))
    n = 0
    for or_id, m in (doc.get("models") or {}).items():
        for e in m.get("endpoints") or []:
            p = e.get("pricing") or {}
            per_m = lambda k: (_f(p.get(k)) * 1e6) if _f(p.get(k)) is not None else None
            lat, tps = e.get("latency_last_30m"), e.get("throughput_last_30m")
            params = set(e.get("supported_parameters") or [])
            conn.execute("""insert into models.endpoints (snapshot_id, gateway, model_id, gateway_model, host, tag, quantization,
                            price_in_1m, price_out_1m, cache_read_1m, context_length, uptime_1d, uptime_30m, status,
                            latency_ms, throughput_tps, tools, structured, service_tier)
                            values (%s,'openrouter',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing""",
                         (sid, m["model_id"], or_id, e.get("provider_name") or "?", e.get("tag") or e.get("provider_name") or "?",
                          e.get("quantization"), per_m("prompt"), per_m("completion"), per_m("input_cache_read"),
                          e.get("context_length"), _f(e.get("uptime_last_1d")), _f(e.get("uptime_last_30m")), e.get("status"),
                          _f(lat.get("p50")) if isinstance(lat, dict) else _f(lat),
                          _f(tps.get("p50")) if isinstance(tps, dict) else _f(tps),
                          "tools" in params, bool({"response_format", "structured_outputs"} & params), e.get("service_tier")))
            n += 1
    conn.execute("update models.snapshots set row_count = %s where snapshot_id = %s", (n, sid))
    return n


def _insert_rows(conn, sid: int, kind: str, doc: dict) -> int:
    """(Re)derive benchmarks/offers of one snapshot from its raw document with the current identity rules."""
    if kind == "or_endpoints":
        return _insert_endpoints(conn, sid, doc)
    conn.execute("delete from models.benchmarks where snapshot_id = %s", (sid,))
    conn.execute("delete from models.offers where snapshot_id = %s", (sid,))
    rows = parse_offers(kind, doc) if kind in OFFER_KINDS else parse_benchmarks(kind, doc)
    for r in rows:
        key = r.get("external_key") or r["offer_key"]
        _ensure_identity(conn, kind, key, r["model_id"],
                         name=r.get("display_name") or (key if kind == "kie" else None))
        _apply_meta(conn, kind, r["model_id"], r.get("meta"))
        if "benchmark" in r:
            conn.execute("""insert into models.benchmarks (snapshot_id, benchmark, task, external_key, model_id, variant,
                            display_name, score, score_unit, cost, cost_unit, released, extra)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing""",
                         (sid, r["benchmark"], r["task"], r["external_key"], r["model_id"], r["variant"], r["display_name"],
                          r["score"], r["score_unit"], r["cost"], r["cost_unit"], r["released"], json.dumps(r["extra"])))
        else:
            conn.execute("""insert into models.offers (snapshot_id, provider, offer_key, model_id, interface, access,
                            price_in_1m, price_out_1m, unit_price, unit, provider_created, pricing,
                            offer_kind, modes, resolution, audio, norm_price, norm_unit)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s) on conflict do nothing""",
                         (sid, r["provider"], r["offer_key"], r["model_id"], r["interface"], r["access"], r["price_in_1m"],
                          r["price_out_1m"], r["unit_price"], r["unit"], r["provider_created"], json.dumps(r["pricing"]),
                          r.get("offer_kind", "generation"), r.get("modes") or [], r.get("resolution"), r.get("audio"),
                          r.get("norm_price"), r.get("norm_unit")))
    conn.execute("update models.snapshots set row_count = %s where snapshot_id = %s", (len(rows), sid))
    return len(rows)


def store(conn, kind: str, doc: dict, fetched_at: datetime, url: str) -> tuple[int, bool]:
    """Insert the snapshot (deduplicated by content) and (re)derive its rows. Returns (snapshot_id, is_new).

    An unchanged document is re-derived anyway, so identity rule changes (aliases.json) apply immediately.
    """
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(blob.encode()).hexdigest()
    found = conn.execute("select snapshot_id from models.snapshots where kind = %s and sha256 = %s", (kind, sha)).fetchone()
    if found:
        sid, new = found["snapshot_id"], False
        conn.execute("update models.snapshots set fetched_at = greatest(fetched_at, %s) where snapshot_id = %s",
                     (fetched_at, sid))
    else:
        sid, new = conn.execute("""insert into models.snapshots (kind, fetched_at, source_url, sha256, row_count, raw)
                                   values (%s, %s, %s, %s, 0, %s::jsonb) returning snapshot_id""",
                                (kind, fetched_at, url, sha, blob)).fetchone()["snapshot_id"], True
    _insert_rows(conn, sid, kind, doc)
    return sid, new
