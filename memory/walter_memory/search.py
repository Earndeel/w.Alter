"""Unified search (P3): SQL filters + multilingual full-text + local vectors, fused with RRF, optional rerank.

Everything points to canonical rows (core.events / core.derived_items / core.objects). The index (search.chunks) is
derived and rebuildable: `walter-memory index --rebuild`.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import threading
import time
from datetime import datetime
from typing import Any

import httpx
import numpy as np

from . import privacy
from .db import connection

INDEXER_VERSION = "1"
MODEL = os.environ.get("WALTER_MEMORY_EMBED_MODEL", "minishlab/potion-multilingual-128M")
# Shared local embedding models, owned by this module (also read by walter-skills).
MODEL_DIR = os.environ.get("WALTER_MEMORY_MODEL_DIR", str(Path(__file__).resolve().parents[1] / "models" / "embeddings"))
TEXT_EVENT_TYPES = ("message.received", "message.sent", "message.edited", "email.received", "email.sent",
                    "calendar.event", "note.recorded", "person.met", "location.stay", "page.visited", "search.performed")
CHUNK = 1500
_embedder = None
_lock = threading.Lock()

STOP = {
    "french": {"le", "la", "les", "des", "est", "et", "que", "pour", "pas", "une", "dans", "qui", "sur", "avec", "je", "tu",
               "vous", "nous", "mais", "du", "au", "ce", "ça", "il", "elle", "mon", "ma", "mes"},
    "english": {"the", "and", "is", "are", "you", "that", "for", "with", "this", "have", "not", "was", "what", "but",
                "they", "will", "your", "it's", "i'm", "can", "from"},
    "spanish": {"el", "los", "las", "que", "por", "una", "para", "con", "pero", "muy", "es", "estoy", "yo"},
    "german": {"der", "die", "das", "und", "ist", "nicht", "ich", "mit", "sie", "ein", "eine", "auch", "wir"},
    "italian": {"il", "che", "non", "una", "sono", "per", "con", "gli", "della", "anche", "io", "è"},
    "portuguese": {"não", "uma", "para", "com", "você", "eu", "mais", "como", "isso", "muito"},
}
WORD = re.compile(r"[\w'’]+", re.U)


def detect_lang(text: str) -> str:
    words = [w.lower() for w in WORD.findall(text[:2000])]
    if len(words) < 3:
        return "simple"
    scores = {lang: sum(w in s for w in words) for lang, s in STOP.items()}
    lang, score = max(scores.items(), key=lambda x: x[1])
    return lang if score >= 2 else "simple"


def embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(MODEL, cache_dir=MODEL_DIR, threads=int(os.environ.get("WALTER_MEMORY_EMBED_THREADS", "2")))
    return _embedder


def embed(texts: list[str]) -> np.ndarray:
    v = np.array(list(embedder().embed(texts, batch_size=256)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-9)


def vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def chunks_of(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= CHUNK:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"(\n\s*\n)", text):
        if len(cur) + len(para) > CHUNK and cur:
            parts.append(cur.strip()); cur = ""
        cur += para
        while len(cur) > CHUNK * 1.5:
            parts.append(cur[:CHUNK]); cur = cur[CHUNK:]
    if cur.strip():
        parts.append(cur.strip())
    return parts


# ───────────────────────────── indexing ─────────────────────────────
def _index_rows(conn, rows: list[dict], kind: str) -> int:
    items = []
    for r in rows:
        for i, part in enumerate(chunks_of(r["text"])):
            if len(part) >= 2:
                items.append((r, i, part))
    if not items:
        return 0
    vecs = embed([p for _, _, p in items])
    with conn.cursor() as cur:
        for (r, i, part), v in zip(items, vecs):
            lang = detect_lang(part)
            cur.execute(
                """insert into search.chunks (kind, ref_id, chunk_no, occurred_at, source, label, thread_id,
                                              actor_identity_id, text, lang, tsv, embedding, privacy_class, hidden,
                                              content_hash, indexer_version)
                   values (%(kind)s, %(ref)s, %(no)s, %(at)s, %(source)s, %(label)s, %(thread)s, %(actor)s, %(text)s, %(lang)s,
                           setweight(to_tsvector('simple', search.f_unaccent(%(text)s)), 'A') ||
                           to_tsvector(%(lang_cfg)s::text::regconfig, %(text)s),
                           %(vec)s::vector, %(privacy)s, %(hidden)s, md5(%(text)s), %(ver)s)
                   on conflict (kind, ref_id, chunk_no) do nothing""",
                {"kind": kind, "ref": r["ref_id"], "no": i, "at": r.get("occurred_at"), "source": r["source"],
                 "label": r["label"], "thread": r.get("thread_id"), "actor": r.get("actor_identity_id"),
                 "text": part, "lang": lang, "lang_cfg": lang, "vec": vec(v),
                 "privacy": privacy.strictest(r["privacy_class"], *(privacy.classify(conn, {"source": r["source"],
                            "categories": {c for c, _ in privacy.detect(part)}})[0] for _ in [0] if privacy.detect(part))),
                 "hidden": bool(r.get("hidden")), "ver": INDEXER_VERSION})
    # cross-source duplicates (same text within 3 minutes, e.g. Telegram seen by Hermes and by Beeper)
    conn.execute("""update search.chunks c set dup_of = o.chunk_id
                    from search.chunks o
                    where c.dup_of is null and c.kind = 'event' and o.kind = 'event' and c.content_hash = o.content_hash
                      and o.chunk_id < c.chunk_id and o.source <> c.source
                      and abs(extract(epoch from c.occurred_at - o.occurred_at)) < 180
                      and c.created_at > now() - interval '10 minutes'""")
    return len(items)


def index_pending(limit: int = 20000) -> dict:
    """Index new canonical rows (events by ingested_at cursor, derived items, object texts)."""
    from . import ingestion
    out = {}
    cp = ingestion.get_checkpoint("search_indexer", "events")
    since = cp.get("ingested_at", "1970-01-01T00:00:00+00:00")
    with connection() as conn:
        # Anti-join on a sliding window rather than a pure cursor: long-running connector transactions commit rows
        # whose ingested_at is older than the cursor, and a cursor alone would skip them (seen 2026-10-01).
        rows = conn.execute("""select e.event_id as ref_id, e.occurred_at, e.ingested_at, e.source, e.event_type as label,
                                      e.thread_id, e.actor_identity_id, e.content as text, e.privacy_class,
                                      exists (select 1 from core.events r where r.event_type = 'event.retracted'
                                              and r.payload @> jsonb_build_object('target_event_id', e.event_id::text)) as hidden
                               from core.events e
                               where e.ingested_at > %s::timestamptz - interval '3 days' and e.event_type = any(%s)
                                 and e.content is not null and length(e.content) > 1
                                 and not exists (select 1 from search.chunks c where c.kind = 'event' and c.ref_id = e.event_id)
                               order by e.ingested_at limit %s""", (since, list(TEXT_EVENT_TYPES), limit)).fetchall()
        out["events"] = _index_rows(conn, rows, "event")
        # retractions arriving after indexing: hide the chunks (the event stays in the journal, readers skip it)
        out["retracted_hidden"] = conn.execute(
            """update search.chunks c set hidden = true from core.events r
               where r.event_type = 'event.retracted' and r.ingested_at > %s::timestamptz - interval '3 days'
                 and c.kind = 'event' and c.ref_id::text = r.payload->>'target_event_id' and not c.hidden""",
            (since,)).rowcount
        if rows:
            ingestion.set_checkpoint("search_indexer", "events", {"ingested_at": rows[-1]["ingested_at"].isoformat()}, conn=conn)
    with connection() as conn:
        rows = conn.execute("""select d.item_id as ref_id, coalesce(d.valid_from, d.created_at) as occurred_at,
                                      d.derived_by as source, d.kind as label, d.content as text, d.privacy_class,
                                      coalesce((d.attributes->>'quarantined')::boolean, false) as hidden
                               from core.derived_items d
                               where d.status in ('legacy_derived','derived','verified') and d.kind not in ('document','signal_candidate')
                                 and not exists (select 1 from search.chunks c where c.kind = 'derived' and c.ref_id = d.item_id)
                               limit %s""", (limit,)).fetchall()
        out["derived"] = _index_rows(conn, rows, "derived")
    with connection() as conn:
        rows = conn.execute("""select o.id as ref_id, o.captured_at as occurred_at, o.source, o.kind as label,
                                      coalesce(o.original_name,'') || E'\\n' || o.derived_text as text, o.privacy_class
                               from core.objects o where o.derived_text is not null and o.purged_at is null
                                 and not exists (select 1 from search.chunks c where c.kind = 'object' and c.ref_id = o.id)
                               limit %s""", (limit,)).fetchall()
        out["objects"] = _index_rows(conn, rows, "object")
    ingestion.mark_success("search_indexer")
    return out


# ───────────────────────────── search ─────────────────────────────
def search(query: str, *, limit: int = 10, sources: list[str] | None = None, labels: list[str] | None = None,
           since: Any = None, until: Any = None, thread_id: str | None = None, include_derived: bool = True,
           max_privacy: str = "local_only", rerank: bool = False, candidates: int = 60) -> list[dict]:
    where, args = ["not c.hidden", "c.dup_of is null", "c.privacy_class = any(%s)"], [privacy.allowed_classes(max_privacy)]
    if sources:
        where.append("c.source = any(%s)"); args.append(sources)
    if labels:
        where.append("c.label = any(%s)"); args.append(labels)
    if since:
        where.append("c.occurred_at >= %s"); args.append(since)
    if until:
        where.append("c.occurred_at < %s"); args.append(until)
    if thread_id:
        where.append("c.thread_id = %s"); args.append(thread_id)
    if not include_derived:
        where.append("c.kind <> 'derived'")
    lang = detect_lang(query)
    qv = vec(embed([query])[0])
    t0 = time.perf_counter()
    # Candidate generation per lane (knowledge = derived items, evidence = events/objects): raw messages vastly
    # outnumber knowledge rows and would crowd them out of a single candidate pool (bench 2026-10-01).
    lanes = [["c.kind = 'derived'"], ["c.kind <> 'derived'"]] if include_derived else [[]]
    per_lane = max(10, candidates // len(lanes))
    scores: dict[int, float] = {}
    with connection() as conn:
        for lane in lanes:
            w = " and ".join(where + lane)
            fts = conn.execute(f"""
                with q as (select websearch_to_tsquery('simple', search.f_unaccent(%s)) ||
                                  websearch_to_tsquery(%s::text::regconfig, %s) as tq)
                select c.chunk_id from search.chunks c, q where {w} and c.tsv @@ q.tq
                order by ts_rank_cd(c.tsv, q.tq) desc limit %s""", (query, lang, query, *args, per_lane)).fetchall()
            if len(fts) < 5:   # OR-relaxed query when the strict form finds little
                words = [x for x in re.findall(r"\w+", search_norm(query)) if len(x) > 2]
                if words:
                    fts += conn.execute(f"""
                        select c.chunk_id from search.chunks c where {w} and c.tsv @@ to_tsquery('simple', %s)
                        order by ts_rank_cd(c.tsv, to_tsquery('simple', %s)) desc limit %s""",
                        (*args, " | ".join(words), " | ".join(words), per_lane)).fetchall()
            sem = conn.execute(f"""select c.chunk_id from search.chunks c where {w} and c.embedding is not null
                                   order by c.embedding <=> %s::vector limit %s""", (*args, qv, per_lane)).fetchall()
            for ranked in (fts, sem):
                seen = set()
                for rank, r in enumerate(ranked):
                    if r["chunk_id"] in seen:
                        continue
                    seen.add(r["chunk_id"])
                    scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0) + 1 / (60 + rank)
        top = sorted(scores, key=scores.get, reverse=True)[:max(limit, candidates if rerank else limit)]
        rows = conn.execute("""select c.chunk_id, c.kind, c.ref_id::text, c.occurred_at, c.source, c.label, c.thread_id,
                                      c.text, c.privacy_class, i.display_name as actor
                               from search.chunks c left join core.source_identities i on i.identity_id = c.actor_identity_id
                               where c.chunk_id = any(%s)""", (top,)).fetchall()
    by_id = {r["chunk_id"]: {**r, "score": scores[r["chunk_id"]]} for r in rows}
    results = [by_id[i] for i in top if i in by_id]
    if max_privacy == 'cloud_allowed':
        from .read_policy import filter_cloud_rows
        with connection() as conn:
            results = filter_cloud_rows(conn, results)
    if rerank and results:
        results = _rerank(query, results, limit)
    for r in results:
        r["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return results[:limit]


def search_norm(text: str) -> str:
    with connection() as conn:
        return conn.execute("select search.f_unaccent(lower(%s)) as t", (text,)).fetchone()["t"]


def _rerank(query: str, results: list[dict], limit: int) -> list[dict]:
    """Rerank only current permitted canonical records; private queries stay local."""
    from .read_policy import filter_cloud_rows, query_privacy
    query_class = query_privacy(query)
    if query_class == 'local_only':
        return results
    with connection() as conn:
        cloud = filter_cloud_rows(conn, results)
    if not cloud:
        return results
    if query_class == 'redacted_cloud':
        query = privacy.redact(query)[0]
    from .llm import _key
    docs = []
    for r in cloud:
        text = r["text"]
        if r["privacy_class"] == "redacted_cloud":
            text, _ = privacy.redact(text, [r.get("actor") or ""])
        docs.append(text[:2000])
    from .llm import router_model
    model = router_model("rerank", "cohere/rerank-4-fast")   # Walter Router poste (2026-10-16)
    try:
        resp = httpx.post("https://openrouter.ai/api/v1/rerank", headers={"Authorization": f"Bearer {_key()}"},
                          json={"model": model, "query": query, "documents": docs, "top_n": min(limit, len(docs))},
                          timeout=8)
        resp.raise_for_status()
        data = resp.json()
        order = [cloud[x["index"]] for x in data["results"]]
        from .llm import _log
        _log(processor="search.rerank", model=model, purpose="rerank", budget="recurring",
             privacy_class="redacted_cloud", cost_usd=(data.get("usage") or {}).get("cost"), status="ok")
    except Exception:
        return results
    rest = [r for r in results if r not in order]
    return order + rest
