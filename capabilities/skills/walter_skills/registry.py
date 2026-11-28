"""The registry: everything walter-skills derives or observes, in Postgres schema `skills` (git keeps only content).

The only module that talks to the database. Small, explicit functions; callers never write SQL.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from contextlib import contextmanager
from typing import Iterator

from walter_memory.db import pool

_down_until = 0.0  # circuit breaker: after a failure, fail fast for a while instead of waiting on every call


class Unavailable(RuntimeError):
    pass


@contextmanager
def db(timeout: float = 3.0) -> Iterator:
    global _down_until
    if time.monotonic() < _down_until:
        raise Unavailable("registry unavailable (circuit open)")
    try:
        with pool().connection(timeout=timeout) as conn:
            with conn.transaction():
                yield conn
    except Unavailable:
        raise
    except Exception as e:
        if "connection" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower() or \
                "PoolTimeout" in type(e).__name__ or "OperationalError" in type(e).__name__:
            _down_until = time.monotonic() + 30
        raise


def qid(message: str) -> str:
    """Stable id of a message (no text stored): the benchmark and every label use it."""
    return hashlib.sha1(re.sub(r"\s+", " ", (message or "").lower())[:500].encode()).hexdigest()[:12]


# ── cards ─────────────────────────────────────────────────────────────────────────────────────────────

def cards() -> dict[str, dict]:
    with db() as c:
        return {r["name"]: r["card"] | {"sha": r["content_sha"]} for r in c.execute("select name, content_sha, card from skills.cards")}


def put_card(name: str, content_sha: str, card: dict, model: str | None, version: str | None) -> None:
    with db() as c:
        c.execute("""insert into skills.cards (name, content_sha, model, version, card) values (%s, %s, %s, %s, %s)
                     on conflict (name) do update set content_sha = excluded.content_sha, model = excluded.model,
                       version = excluded.version, card = excluded.card, created_at = now()""",
                  (name, content_sha, model, version, json.dumps(card, ensure_ascii=False)))


# ── labels (the truth the ranker learns from) ─────────────────────────────────────────────────────────

def put_labels(q: str, labels: dict[str, int], source: str, weight: float = 1.0, runtime: str | None = None,
               evidence: dict | None = None) -> int:
    rows = [(q, s, int(v), source, weight, runtime, json.dumps(evidence or {})) for s, v in labels.items()]
    if not rows:
        return 0
    with db() as c:
        c.cursor().executemany(
            """insert into skills.labels (qid, skill, label, source, weight, runtime, evidence)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (qid, skill, source) do update set label = excluded.label, weight = excluded.weight,
                 at = now(), evidence = excluded.evidence""", rows)
    return len(rows)


def labels(sources: tuple[str, ...] = ("bench", "judge", "implicit", "miss")) -> dict[str, dict[str, tuple[int, float]]]:
    """qid → {skill: (label, weight)}; when several sources label the same pair, the explicit judge wins."""
    rank = {"bench": 3, "judge": 3, "miss": 2, "implicit": 1}
    out: dict[str, dict[str, tuple[int, float, int]]] = {}
    with db() as c:
        for r in c.execute("select qid, skill, label, weight, source from skills.labels where source = any(%s)",
                           (list(sources),)):
            cur = out.setdefault(r["qid"], {}).get(r["skill"])
            if cur is None or rank[r["source"]] > cur[2]:
                out[r["qid"]][r["skill"]] = (r["label"], r["weight"], rank[r["source"]])
    return {q: {s: (v[0], v[1]) for s, v in d.items()} for q, d in out.items()}


def label_counts() -> dict[str, int]:
    with db() as c:
        return {r["source"]: r["n"] for r in c.execute("select source, count(distinct qid) n from skills.labels group by 1")}


def labelled_qids(source: str) -> set[str]:
    with db() as c:
        return {r["qid"] for r in c.execute("select distinct qid from skills.labels where source = %s", (source,))}


# ── rankers ───────────────────────────────────────────────────────────────────────────────────────────

def save_ranker(version: str, blob: bytes, encoder: str, learner: str, skills: int, metrics: dict,
                state: str = "candidate") -> None:
    with db() as c:
        c.execute("""insert into skills.rankers (version, state, encoder, learner, skills, metrics, blob)
                     values (%s, %s, %s, %s, %s, %s, %s)""",
                  (version, state, encoder, learner, skills, json.dumps(metrics), blob))


def ranker(version: str | None = None) -> dict | None:
    with db() as c:
        if version:
            return c.execute("select * from skills.rankers where version = %s", (version,)).fetchone()
        return c.execute("select * from skills.rankers where state = 'active'").fetchone()


def set_ranker_state(version: str, state: str, metrics: dict | None = None) -> None:
    with db() as c:
        if state == "active":
            c.execute("update skills.rankers set state = 'retired' where state = 'active' and version <> %s", (version,))
            c.execute("update skills.rankers set state = 'active', promoted_at = now() where version = %s", (version,))
        else:
            c.execute("update skills.rankers set state = %s where version = %s", (state, version))
        if metrics is not None:
            c.execute("update skills.rankers set metrics = metrics || %s where version = %s",
                      (json.dumps(metrics), version))
        c.execute("delete from skills.rankers where state in ('retired', 'rejected') and version not in "
                  "(select version from skills.rankers where state in ('retired', 'rejected') order by created_at desc limit 5)")


# ── state, ledger, journals ───────────────────────────────────────────────────────────────────────────

def get_state(key: str, default=None):
    with db() as c:
        r = c.execute("select value from skills.state where key = %s", (key,)).fetchone()
    return r["value"] if r else default


def set_state(key: str, value) -> None:
    with db() as c:
        c.execute("""insert into skills.state (key, value) values (%s, %s)
                     on conflict (key) do update set value = excluded.value, updated_at = now()""",
                  (key, json.dumps(value, default=str)))


def ledger(actor: str, action: str, name: str | None = None, commit: str | None = None, evidence: dict | None = None) -> None:
    with db() as c:
        c.execute("insert into skills.ledger (actor, action, name, git_commit, evidence) values (%s, %s, %s, %s, %s)",
                  (actor, action, name, commit, json.dumps(evidence or {}, ensure_ascii=False, default=str)))


def journal_retrieval(runtime: str | None, session_id: str | None, mode: str, message: str, results: list[dict],
                      shown: list[str], latency_ms: int, model: str) -> int | None:
    with db() as c:
        r = c.execute(
            """insert into skills.retrievals (runtime, session_id, mode, query_sha, query_chars, results, injected,
                                              latency_ms, model)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            (runtime, session_id, mode, qid(message), len(message or ""),
             json.dumps([{"name": x["name"], "score": x["score"]} for x in results]), shown, latency_ms, model)).fetchone()
    return r["id"] if r else None


def recently_shown(session_id: str | None, turns: int) -> tuple[set[str], int]:
    """Cards shown to this session in its last `turns` injections (6 h window) and how many injections it had."""
    if not session_id:
        return set(), 0
    with db() as c:
        rows = c.execute("""select injected from skills.retrievals where session_id = %s and mode = 'inject'
                            and at > now() - interval '6 hours' order by at desc limit %s""",
                         (session_id, turns)).fetchall()
    return {n for r in rows for n in (r["injected"] or [])}, len(rows)


def journal_read(runtime: str | None, session_id: str | None, name: str, via: str) -> None:
    with db() as c:
        c.execute("insert into skills.reads (runtime, session_id, name, via) values (%s, %s, %s, %s)",
                  (runtime, session_id, name, via))


def refresh_catalog(rows: list[dict]) -> int:
    with db() as c:
        for r in rows:
            c.execute(
                """insert into skills.catalog (name, state, domain, owner, origin, description, summary, path,
                                               content_sha, card_sha, meta, updated_at)
                   values (%(name)s, %(state)s, %(domain)s, %(owner)s, %(origin)s, %(description)s, %(summary)s,
                           %(path)s, %(content_sha)s, %(card_sha)s, %(meta)s, now())
                   on conflict (name) do update set state = excluded.state, domain = excluded.domain,
                     owner = excluded.owner, origin = excluded.origin, description = excluded.description,
                     summary = excluded.summary, path = excluded.path, card_sha = excluded.card_sha,
                     meta = excluded.meta,
                     updated_at = case when skills.catalog.content_sha is distinct from excluded.content_sha
                                       or skills.catalog.state is distinct from excluded.state then now()
                                       else skills.catalog.updated_at end,
                     content_sha = excluded.content_sha""", r)
        c.execute("delete from skills.catalog where not (name = any(%s))", ([r["name"] for r in rows],))
    return len(rows)
