"""Unified search (P3): SQL filters + multilingual full-text + local vectors, fused with RRF, optional rerank.

Everything points to canonical rows (core.events / core.derived_items / core.objects). The index (search.chunks) is
derived and rebuildable: `walter-memory index --rebuild`.
"""
from __future__ import annotations

import hashlib
import math
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
AGENT_SOURCES = ("hermes", "codex", "claude_code", "dsh")
# Recall noise (2026-10-19): rows that stay in core.events (append-only history) but are kept out of the index's
# readable part — hidden with a reason, recomputed by `walter-memory index --hide-noise`. Generic runtime artefacts
# only (no personal content): harness injections, transcript replays, tool output, memory blocks already injected.
NOISE = [
    ("injected_memory", re.compile(r"Mémoire W\.Alter \(injectée|^## Mémoire pertinente|## Mémoire pertinente\\n|"
                                   r"Contexte historique daté, à confronter", re.M)),
    ("agent_replay", re.compile(r"^(The following is the Codex agent history|\[\d+\] (user|assistant|tool|system|developer)\b)")),
    ("runtime_injection", re.compile(
        r"^(\[(Your active task list was preserved|CONTEXT COMPACTION|PRIOR CONTEXT|System: |ASYNC DELEGATION BATCH COMPLETE|"
        r"Continuing toward your standing goal|Escalade depuis session vocale)|## Hermes Memory Layers|"
        r"You've reached the maximum number of tool-call|You just executed tool calls but returned an|"
        r"Operation interrupted|\(empty\)\s*$|Historique de la conversation vocale|Tu es W\.Alter/Hermes, le cerveau profond)"
        r"|## Historical Task Snapshot")),
]
TOOL_OUTPUT = re.compile(r'^\s*[\[{]\s*"')
MIN_WORDS = 3


def noise_reason(text: str, source: str = "") -> str | None:
    """Why an event's text is not recall material (None = index it as readable evidence)."""
    t = (text or "").strip()
    for reason, rx in NOISE:
        if rx.search(t):
            return reason
    if source in AGENT_SOURCES and TOOL_OUTPUT.match(t):
        return "tool_output"
    if len([w for w in WORD.findall(t[:200]) if len(w) > 1]) < MIN_WORDS:
        return "too_short"
    return None


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
# Words that carry no subject in a question (unaccented, lowercase). Generic French/English grammar only.
QUERY_STOP = set("""le la les l un une des du de d au aux et ou est sont ce cet cette ces c ca qu que qui quoi quel quelle
quels quelles comment ou pourquoi quand combien je j me m mon ma mes moi tu te t ton ta tes toi il elle on nous vous ils
elles son sa ses leur leurs y en ne n pas plus avec pour par sur dans a ai as avez avons ont etre etait fait faire
faut doit dois veut veux peut peux s se sais the an is are was were what who whom how why when where which do does
did i my me you your it its of to in on for with and or be can should""".split())
RARE_DF = 5000      # a keyword in more chunks than this is too common to rank on (no IDF in ts_rank_cd)


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
def _hidden_reason(r: dict, kind: str) -> str | None:
    if r.get("hidden"):
        return "quarantined" if kind == "derived" else "retracted"
    reason = noise_reason(r["text"], r["source"]) if kind == "event" else None
    return f"noise:{reason}" if reason else None


def _index_rows(conn, rows: list[dict], kind: str) -> int:
    items = []
    for r in rows:
        r["hidden_reason"] = _hidden_reason(r, kind)   # whole row: a replay's later chunks don't carry the marker
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
                                              hidden_reason, content_hash, indexer_version, generation)
                   values (%(kind)s, %(ref)s, %(no)s, %(at)s, %(source)s, %(label)s, %(thread)s, %(actor)s, %(text)s, %(lang)s,
                           setweight(to_tsvector('simple', search.f_unaccent(%(text)s)), 'A') ||
                           to_tsvector(%(lang_cfg)s::text::regconfig, %(text)s),
                           %(vec)s::vector, %(privacy)s, %(hidden)s, %(reason)s, md5(%(text)s), %(ver)s, %(gen)s)
                   on conflict (kind, ref_id, chunk_no) do nothing""",
                {"kind": kind, "ref": r["ref_id"], "no": i, "at": r.get("occurred_at"), "source": r["source"],
                 "label": r["label"], "thread": r.get("thread_id"), "actor": r.get("actor_identity_id"),
                 "text": part, "lang": lang, "lang_cfg": lang, "vec": vec(v),
                 "privacy": privacy.strictest(r["privacy_class"], *(privacy.classify(conn, {"source": r["source"],
                            "categories": {c for c, _ in privacy.detect(part)}})[0] for _ in [0] if privacy.detect(part))),
                 "hidden": r["hidden_reason"] is not None, "reason": r["hidden_reason"], "ver": INDEXER_VERSION,
                 "gen": r.get("generation") if kind == "derived" else None})
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
            """update search.chunks c set hidden = true, hidden_reason = 'retracted' from core.events r
               where r.event_type = 'event.retracted' and r.ingested_at > %s::timestamptz - interval '3 days'
                 and c.kind = 'event' and c.ref_id::text = r.payload->>'target_event_id'
                 and c.hidden_reason is distinct from 'retracted'""",
            (since,)).rowcount
        if rows:
            ingestion.set_checkpoint("search_indexer", "events", {"ingested_at": rows[-1]["ingested_at"].isoformat()}, conn=conn)
    with connection() as conn:
        rows = conn.execute("""select d.item_id as ref_id, coalesce(d.valid_from, d.created_at) as occurred_at,
                                      d.derived_by as source, d.kind as label, d.content as text, d.privacy_class,
                                      d.generation,
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


READABLE_INDEXED = ("legacy_derived", "derived", "verified")
OWN_CHUNKS = ("document", "signal_candidate")      # never indexed as derived (index_pending skips them too)


def reindex_derived(item_ids: list[str]) -> dict:
    """The index follows a knowledge item that changed (2026-11-09, g1 audit): index_pending only indexes items without
    chunks, so an updated item kept its first text (unfindable as it now reads: the read check drops a stale fragment)
    and a superseded / retracted one kept its chunks. Per item: chunks identical to its current text → nothing; else
    its chunks are replaced, or removed when the item is no longer readable. The index is derived: rebuildable."""
    out = {"unchanged": 0, "reindexed": 0, "removed": 0, "skipped": 0}
    with connection() as conn:
        rows = conn.execute("""select d.item_id as ref_id, coalesce(d.valid_from, d.created_at) as occurred_at,
                                      d.derived_by as source, d.kind as label, d.content as text, d.privacy_class,
                                      d.generation, d.status, d.kind,
                                      coalesce((d.attributes->>'quarantined')::boolean, false) as hidden
                               from core.derived_items d where d.item_id = any(%s::uuid[])""",
                            ([str(i) for i in item_ids],)).fetchall()
        for r in rows:
            if r["kind"] in OWN_CHUNKS:
                out["skipped"] += 1
                continue
            have = [c["text"] for c in conn.execute("""select text from search.chunks where kind = 'derived' and ref_id = %s
                                                       order by chunk_no""", (r["ref_id"],))]
            readable = r["status"] in READABLE_INDEXED
            want = [p for p in chunks_of(r["text"] or "") if len(p) >= 2] if readable else []
            if have == want:
                out["unchanged"] += 1
                continue
            conn.execute("delete from search.chunks where kind = 'derived' and ref_id = %s", (r["ref_id"],))
            if want:
                _index_rows(conn, [r], "derived")
                out["reindexed"] += 1
            else:
                out["removed"] += 1
    return out


def stale_derived(limit: int = 5000) -> list[str]:
    """Derived items whose chunks no longer match them (reconciliation and the one-off catch-up of 2026-11-09)."""
    with connection() as conn:
        return [r["id"] for r in conn.execute("""
            select distinct d.item_id::text id from search.chunks c join core.derived_items d on d.item_id = c.ref_id
            where c.kind = 'derived' and d.kind <> all(%s)
              and (d.status <> all(%s) or position(btrim(c.text) in btrim(d.content)) = 0)
            limit %s""", (list(OWN_CHUNKS), list(READABLE_INDEXED), limit))]


def hide_noise(batch: int = 5000) -> dict:
    """Recompute noise for every indexed event (after a NOISE rule change): hide new noise, un-hide what no longer
    matches. Reads the canonical content; never touches core.events, retractions or derived quarantine."""
    import collections
    changes: dict[str, str | None] = {}
    with connection() as conn:
        rows = conn.execute("""select ref_id, source, string_agg(text, '' order by chunk_no) as text,
                                      max(hidden_reason) as reason
                               from search.chunks where kind = 'event'
                                 and (hidden_reason is null or hidden_reason like 'noise:%%')
                               group by ref_id, source""").fetchall()
    for r in rows:
        reason = noise_reason(r["text"], r["source"])
        reason = f"noise:{reason}" if reason else None
        if reason != r["reason"]:
            changes[str(r["ref_id"])] = reason
    out = collections.Counter(v or "unhidden" for v in changes.values())
    items = list(changes.items())
    for i in range(0, len(items), batch):
        with connection() as conn:
            conn.execute("""update search.chunks c set hidden = (v.reason is not null), hidden_reason = v.reason
                            from unnest(%s::uuid[], %s::text[]) v(ref_id, reason)
                            where c.kind = 'event' and c.ref_id = v.ref_id""",
                         ([k for k, _ in items[i:i + batch]], [v for _, v in items[i:i + batch]]))
    return {"scanned": len(rows), **out}


# ───────────────────────────── search ─────────────────────────────
# Candidate generation per lane (knowledge = derived items, evidence = events/objects): raw messages vastly outnumber
# knowledge rows and would crowd them out of a single candidate pool (bench 2026-10-01). Each predicate matches a
# partial HNSW index (migration 013).
LANES = {"knowledge": "c.kind = 'derived'", "evidence": "c.kind <> 'derived'"}
# Conversation narratives and open tasks rank below atomic facts (bench 2026-10-19: +2 hits locally on 30 questions);
# they stay findable, e.g. when nothing atomic matches.
LABEL_WEIGHT = {"summary": 0.5, "open_loop": 0.5}


def search_lanes(query: str, *, lanes: tuple[str, ...] = ("knowledge", "evidence"), limit: int = 10,
                 sources: list[str] | None = None, labels: list[str] | None = None, since: Any = None,
                 until: Any = None, thread_id: str | None = None, max_privacy: str = "local_only",
                 candidates: int = 60, generations: list[str] | None = None) -> dict[str, list[dict]]:
    """Hybrid search (FTS + vectors fused by RRF) per lane, each lane ranked on its own. For cloud callers every row
    is checked against its canonical owner (read_policy) before the cut, so a filtered row doesn't shorten the list."""
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
    if generations is not None:   # memory generations (P1.0): interpretations of the readable generations; evidence always
        where.append("(c.generation is null or c.generation = any(%s))"); args.append(generations)
    qv = vec(embed([query])[0])
    out: dict[str, list[dict]] = {}
    with connection() as conn:
        # filtered HNSW scans keep walking the graph until enough rows pass the filters (pgvector >= 0.8)
        conn.execute("set local hnsw.ef_search = 100")
        conn.execute("set local hnsw.iterative_scan = relaxed_order")
        kws = keywords(conn, query)
        for lane in lanes:
            w = " and ".join(where + [LANES[lane]])
            fts = _fts(conn, w, args, kws, candidates)
            sem = conn.execute(f"""select chunk_id, label from (
                                       select c.chunk_id, c.label, c.embedding <=> %s::vector as d from search.chunks c
                                       where {w} and c.embedding is not null order by d limit %s) x order by d""",
                               (qv, *args, candidates)).fetchall()
            scores: dict[int, float] = {}
            for ranked in (fts, sem):
                seen = set()
                for rank, r in enumerate(ranked):
                    if r["chunk_id"] in seen:
                        continue
                    seen.add(r["chunk_id"])
                    scores[r["chunk_id"]] = scores.get(r["chunk_id"], 0) + 1 / (60 + rank) * LABEL_WEIGHT.get(r["label"], 1)
            top = sorted(scores, key=scores.get, reverse=True)[:max(limit * 2, limit + 10)]
            rows = conn.execute("""select c.chunk_id, c.kind, c.ref_id::text, c.occurred_at, c.source, c.label,
                                          c.thread_id, c.text, c.privacy_class, c.generation, i.display_name as actor
                                   from search.chunks c left join core.source_identities i
                                     on i.identity_id = c.actor_identity_id
                                   where c.chunk_id = any(%s)""", (top,)).fetchall()
            by_id = {r["chunk_id"]: {**r, "score": scores[r["chunk_id"]], "lane": lane} for r in rows}
            ranked_rows = [by_id[i] for i in top if i in by_id]
            if max_privacy == "cloud_allowed":
                from .read_policy import filter_cloud_rows
                ranked_rows = filter_cloud_rows(conn, ranked_rows, generations=generations)
            out[lane] = ranked_rows[:limit]
    return out


def keywords(conn, query: str) -> list[tuple[str, float]]:
    """Subject words of the query with an IDF weight, rarest first (doc frequency capped at RARE_DF, GIN-counted).
    Question phrasing ("qu'est-ce que", "quel est mon") must not be required by the full-text match."""
    norm = conn.execute("select search.f_unaccent(lower(%s)) as t", (query,)).fetchone()["t"]
    words = list(dict.fromkeys(x for x in re.findall(r"\w+", norm) if len(x) > 1 and x not in QUERY_STOP))
    out = []
    # prefix match from 5 letters: plural / conjugation without a stemmer on the unaccented 'simple' lexemes
    for w in (re.sub(r"(?<=\w{4})[sx]$", "", x) + ":*" if len(x) >= 5 else x for x in words[:8]):
        df = conn.execute("""select count(*) as n from (select 1 from search.chunks
                             where tsv @@ to_tsquery('simple', %s) limit %s) x""", (w, RARE_DF)).fetchone()["n"]
        if df:
            out.append((w, math.log(1 + RARE_DF / df)))
    return sorted(out, key=lambda x: -x[1])


def _fts(conn, where: str, args: list, kws: list[tuple[str, float]], limit: int) -> list[dict]:
    """All subject words first; if that finds little, any rare word, ranked by the summed IDF of the words matched."""
    if not kws:
        return []
    every = " & ".join(w for w, _ in kws)
    rows = conn.execute(f"""select c.chunk_id, c.label from search.chunks c where {where} and c.tsv @@ to_tsquery('simple', %s)
                            order by ts_rank_cd(c.tsv, to_tsquery('simple', %s)) desc limit %s""",
                        (*args, every, every, limit)).fetchall()
    rare = [(w, idf) for w, idf in kws if idf > math.log(2)]      # df < RARE_DF
    if len(rows) >= 5 or len(kws) < 2 or not rare:
        return rows
    score = " + ".join(f"(case when c.tsv @@ to_tsquery('simple', %s) then {idf:.4f} else 0 end)" for _, idf in rare)
    more = conn.execute(f"""select c.chunk_id, c.label from search.chunks c where {where} and c.tsv @@ to_tsquery('simple', %s)
                            order by {score} desc, ts_rank_cd(c.tsv, to_tsquery('simple', %s)) desc limit %s""",
                        (*args, " | ".join(w for w, _ in rare), *(w for w, _ in rare),
                         " | ".join(w for w, _ in rare), limit)).fetchall()
    seen = {r["chunk_id"] for r in rows}
    return rows + [r for r in more if r["chunk_id"] not in seen]


def search(query: str, *, limit: int = 10, sources: list[str] | None = None, labels: list[str] | None = None,
           since: Any = None, until: Any = None, thread_id: str | None = None, include_derived: bool = True,
           max_privacy: str = "local_only", rerank: bool = False, candidates: int = 60,
           lanes: tuple[str, ...] | None = None, history: bool = False,
           generations: list[str] | None = None) -> list[dict]:
    """Both lanes fused by score (or the given lanes), optionally reranked. Derived knowledge comes from the readable
    memory generations; history=True reads every generation (pre-V1 interpretations included, labelled);
    `generations` narrows the read set (Context's g1_first read: one pool per generation)."""
    from .generations import read_set
    t0 = time.perf_counter()
    gens = read_set(history)
    if generations is not None:
        gens = [g for g in generations if gens is None or g in gens]
    lanes = lanes or (("knowledge", "evidence") if include_derived else ("evidence",))
    per_lane = search_lanes(query, lanes=lanes, limit=max(limit, candidates if rerank else limit), sources=sources,
                            labels=labels, since=since, until=until, thread_id=thread_id, max_privacy=max_privacy,
                            candidates=max(10, candidates // len(lanes)), generations=gens)
    results = sorted((r for rows in per_lane.values() for r in rows), key=lambda r: r["score"], reverse=True)
    if rerank and results:
        results = _rerank(query, results, limit)
    for r in results:
        r["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return results[:limit]


def dedupe(rows: list[dict], threshold: float = 0.88) -> list[dict]:
    """Drop exact and near-duplicate texts, keeping the first (best-ranked): legacy memories repeat the same fact
    with small variations, and the same message is often stored by several sessions."""
    seen, unique = set(), []
    for r in rows:
        key = re.sub(r"\W+", " ", (r.get("text") or "").lower()).strip()
        if key and key not in seen:
            seen.add(key); unique.append(r)
    if len(unique) < 2:
        return unique
    v = embed([re.sub(r"\s*\|.*$", "", r["text"])[:400] for r in unique])
    keep: list[int] = []
    for i in range(len(unique)):
        if all(float(v[i] @ v[j]) < threshold for j in keep):
            keep.append(i)
    return [unique[i] for i in keep]


def search_norm(text: str) -> str:
    with connection() as conn:
        return conn.execute("select search.f_unaccent(lower(%s)) as t", (text,)).fetchone()["t"]


RERANK_VERSION = "2"


def rerank_pools(query: str, pools: dict[str, tuple[list[dict], int]], timeout: float = 8) -> dict[str, list[dict]]:
    """Several candidate lists for one query (context sections), reranked by ONE call over their union, then cut
    back per list: each list keeps only its own rows, in the reranked order, up to its limit. One get_context used to
    make 3-4 rerank calls over 60 candidates each; a single larger pool costs less and finds more (07/11: « modèles
    non censurés » reached the Venice decision only with ~150 candidates)."""
    union, seen = [], set()
    for rows, _ in pools.values():
        for r in rows:
            k = (r.get("ref_id"), r.get("text"))
            if k not in seen:
                seen.add(k); union.append(r)
    ranked = _rerank(query, union, len(union), timeout) if union else []
    pos = {(r.get("ref_id"), r.get("text")): i for i, r in enumerate(ranked)}
    for r in union:                    # the row's place in the whole union (g1_first compares generations with it)
        r["union_rank"] = pos.get((r.get("ref_id"), r.get("text")), len(pos))
    return {name: sorted(rows, key=lambda r: pos.get((r.get("ref_id"), r.get("text")), len(pos)))[:limit]
            for name, (rows, limit) in pools.items()}


def _rerank(query: str, results: list[dict], limit: int, timeout: float = 8) -> list[dict]:
    """Rerank only current permitted canonical records; private queries stay local."""
    from .read_policy import filter_cloud_rows, query_privacy
    query_class = query_privacy(query)
    if not privacy.model_may_receive(query_class):
        return results
    query = privacy.mask_secrets(query)
    with connection() as conn:
        cloud = filter_cloud_rows(conn, results)
    if not cloud:
        return results
    if query_class == 'redacted_cloud' and privacy.pseudonymise():
        query = privacy.redact(query)[0]
    docs = []
    for r in cloud:
        text = r["text"]
        if r["privacy_class"] == "redacted_cloud" and privacy.pseudonymise():
            text, _ = privacy.redact(text, [r.get("actor") or ""])
        docs.append(text[:2000])
    if len(cloud) < 2:
        return results
    from . import llm, processing
    top_n = min(limit, len(docs))

    def call():
        # Walter Router's `rerank` poste, executed by the walter-llm gateway (SOCLE A6): the model and its fallbacks
        # are the Router's; llm.rerank books the call in system.model_calls.
        out = llm.rerank(query, docs, top_n=top_n, processor="search.rerank", privacy_class="redacted_cloud",
                         timeout=timeout)
        return [int(x["index"]) for x in out["results"]], out.get("model")
    # The same query over the same documents is never sent twice (a hook and a pack for one message, a bench rerun):
    # the ledger keeps the order only (indices), keyed by a hash of the poste, query and documents (version 2: the
    # model is the Router's choice, known after the call; a poste change is a new RERANK_VERSION).
    inputs = {"poste": "rerank", "query": query, "top_n": top_n,
              "docs": [hashlib.sha256(d.encode()).hexdigest()[:24] for d in docs]}
    try:
        idx, _ = processing.decide_once("search.rerank", RERANK_VERSION, inputs, call,
                                        privacy_class="redacted_cloud")
        order = [cloud[i] for i in idx if 0 <= i < len(cloud)]
    except Exception:
        return results
    rest = [r for r in results if r not in order]
    return order + rest
