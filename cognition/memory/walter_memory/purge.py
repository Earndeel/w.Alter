"""Break-glass purge (A9): really delete a secret or wrongly ingested data from Walter Memory, and keep it deleted.

Normal history is append-only; this is the explicit, traced exception, and the only door that deletes from
core.events (the guard yields to `walter.purge` for the purge's own transaction only). Dry run by default.

What one executed purge covers, in one transaction (policy of 2026-11-09, cleanup phase 2):
  - core.events selected (ids, or a pattern over content and payload). Their idempotence keys in core.event_keys
    STAY, as tombstones (source, source_id, type, no content): a connector re-reading the source finds the key and
    inserts nothing, so the event cannot come back by ingestion;
  - knowledge citing them (core.derived_items), its evidence rows (views.evidence), and the versions of a view built
    on that knowledge from the moment it existed: content replaced by a marker and marked stale (consolidate rebuilds
    it without them); older versions of the same view, which cannot quote it, stay intact; knowledge the purged
    knowledge had superseded becomes current again (as if the purged statement had never been made);
  - derived copies: search.chunks, processing.decisions referring to them, extraction.covered, their ids in
    extraction.segments, triage.decisions, privacy.detections references;
  - Raw Vault objects: bytes deleted (Drive trash emptied), registry row marked purged;
  - walter_logs (pattern only): matching rows keep their event_key but text and data are replaced by a marker (the
    journal's writer is idempotent on that key: re-reading a runtime's transcript cannot re-insert them).
Ledger: what was removed, by identifier only (never content, never the pattern: only its sha256), in
  system.purge_ledger AND in the instance file @instance/state/memory/purge-ledger.jsonl (0600, backed up by restic),
  because a database restored from before the purge does not carry the table.
Restored data: `purge reapply` re-applies every ledger entry (and re-runs ledger operations such as the observability
  retirement); `purge verify`, also run by `walter-memory health`, reports any purged target present again. After ANY
  restore of the database: reapply, then verify (RUNBOOK § Purge).
Backups: never modified automatically. `exposure()` lists the backups that may still hold purged data and until when
  rotation keeps them. `rotate_local_dumps=True` (explicit) takes a fresh dump, then shreds the OLDER rolling local
  dumps only. Restic snapshots, keep-tagged snapshots, phase archives (memory-archive), restore points (changes/) and
  the retired age archives on Drive are never touched by code: definitive removal from them is a manual procedure
  that Monsieur decides (RUNBOOK § Purge); until then the ledger prevents a silent reintroduction on restore.
Outside Memory: the runtimes' own stores (Hermes state.db, Claude Code / Codex transcripts) and the daily raw Hermes
  exports in the Raw Vault belong to their owners (RUNBOOK § Purge lists them); the tombstones above keep Memory clean
  whatever they still hold.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

from .db import connect

LEDGER_ENV = "WALTER_MEMORY_PURGE_LEDGER"
KINDS = ("event", "derived", "object", "walter_logs")
COUNT_KEYS = {"event": "events", "derived": "derived", "object": "objects", "walter_logs": "walter_logs"}  # history
MARK = "«purgé»"


def _fp(values) -> list[str]:
    return [hashlib.sha256(str(v).encode()).hexdigest() for v in values]


def _instance(*parts: str) -> Path | None:
    try:
        p = subprocess.run(["walter", "instance", "path", *parts], capture_output=True, text=True,
                           timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        p = ""
    return Path(p) if p else None


# ── ledger ────────────────────────────────────────────────────────────────────────────────────────────────────────
def ledger_path() -> Path:
    if os.environ.get(LEDGER_ENV):
        return Path(os.environ[LEDGER_ENV])
    base = _instance("state", "memory")
    if base is None:
        raise RuntimeError(f"instance state path unknown (walter instance path state memory): set {LEDGER_ENV}")
    return base / "purge-ledger.jsonl"


def ledger_append(entry: dict) -> None:
    """One JSON line per (purge, kind): identifiers only. Append-only, fsynced, 0600."""
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(p, 0o600)


def ledger(conn) -> dict[str, set[str]]:
    """Union of the database ledger and the instance file (the file survives a restore of an older database)."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    if conn.execute("select to_regclass('system.purge_ledger') t").fetchone()["t"]:
        for r in conn.execute("select kind, target from system.purge_ledger"):
            out[r["kind"]].add(r["target"])
    p = ledger_path()
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                out[e["kind"]].update(e["targets"])
    return out


# ── selection ─────────────────────────────────────────────────────────────────────────────────────────────────────
def select_targets(conn, *, event_ids=None, object_refs=None, pattern=None, sessions=None, derived_ids=None) -> dict:
    t = {k: [] for k in KINDS}
    if derived_ids:   # one piece of knowledge (e.g. a run experience of a test conversation)
        t["derived"] += [r["item_id"] for r in conn.execute(
            "select item_id from core.derived_items where item_id = any(%s::uuid[])", (list(derived_ids),)).fetchall()]
    if sessions:      # whole walter_logs sessions (a test conversation): every keyed row is masked
        t["walter_logs"] += [f"{r['session_id']}#{r['event_key']}" for r in conn.execute(
            "select session_id, event_key from walter_logs.events where session_id = any(%s) and event_key is not null",
            (list(sessions),)).fetchall()]
    if event_ids:
        t["event"] += [r["event_id"] for r in conn.execute(
            "select event_id from core.events where event_id = any(%s::uuid[])", (event_ids,)).fetchall()]
    if pattern:
        t["event"] += [r["event_id"] for r in conn.execute(
            "select event_id from core.events where content ~* %s or payload::text ~* %s", (pattern, pattern)).fetchall()]
        t["object"] += [r["id"] for r in conn.execute(
            "select id from core.objects where purged_at is null and (derived_text ~* %s or original_name ~* %s)",
            (pattern, pattern)).fetchall()]
        t["derived"] += [r["item_id"] for r in conn.execute(
            "select item_id from core.derived_items where content ~* %s", (pattern,)).fetchall()]
        t["walter_logs"] += [f"{r['session_id']}#{r['event_key']}" for r in conn.execute(
            """select session_id, event_key from walter_logs.events
               where event_key is not null and (text ~* %s or data::text ~* %s)""", (pattern, pattern)).fetchall()]
    if object_refs:
        t["object"] += [r["id"] for r in conn.execute(
            "select id from core.objects where id::text = any(%s) or sha256 = any(%s)", (object_refs, object_refs)).fetchall()]
    if t["event"]:
        t["derived"] += [r["item_id"] for r in conn.execute(
            "select item_id from core.derived_items where source_event_ids && %s::uuid[]", (t["event"],)).fetchall()]
    if t["derived"]:
        t["derived"] += _built_from(conn, [str(x) for x in t["derived"]], t["event"], pattern)
    return {k: sorted({str(x) for x in v}) for k, v in t.items()}


def _built_from(conn, derived: list[str], events: list, pattern: str | None) -> list[str]:
    """Knowledge built only from other knowledge (no source event of its own: an episode's facets…) that sits in a
    view citing the purged knowledge and quotes it (`_quotes`) goes with it — 20/11: the facets of a purged plan's
    episode kept naming the test contact. Knowledge with its own sources is never taken this way: it is purged only
    through its events, an id or the pattern."""
    quotes = _quotes(conn, derived, events, pattern)
    if not quotes:
        return []
    found: set[str] = set()
    frontier = set(derived)
    for _ in range(3):    # facet of an episode of a plan…: a few levels at most
        rows = conn.execute(
            """select distinct d.item_id::text id, d.content from views.evidence e
               join views.evidence e2 on e2.view_key = e.view_key and e2.ref_kind = 'derived'
               join core.derived_items d on d.item_id::text = e2.ref_id
               where e.ref_kind = 'derived' and e.ref_id = any(%s::text[]) and not (e2.ref_id = any(%s::text[]))
                 and cardinality(d.source_event_ids) = 0""",
            (sorted(frontier), sorted(set(derived) | found))).fetchall()
        new = {r["id"] for r in rows if _quoted(r["content"], quotes)}
        if not new:
            break
        found |= new
        frontier = new
    return sorted(found)


def present(conn, led: dict[str, set[str]]) -> dict:
    """The ledger targets that exist again (restored, or never removed): what reapply would remove."""
    ev, dv, ob, wl = (sorted(led.get(k, ())) for k in KINDS)
    out = {k: [] for k in KINDS}
    if ev:
        out["event"] = [str(r["event_id"]) for r in conn.execute(
            "select event_id from core.events where event_id = any(%s::uuid[])", (ev,))]
    if ev or dv:
        out["derived"] = [str(r["item_id"]) for r in conn.execute(
            """select item_id from core.derived_items where item_id = any(%s::uuid[])
                  or (cardinality(%s::uuid[]) > 0 and source_event_ids && %s::uuid[])""", (dv, ev, ev))]
    if ob:
        out["object"] = [str(r["id"]) for r in conn.execute(
            "select id from core.objects where id = any(%s::uuid[]) and purged_at is null", (ob,))]
    if wl:
        s, k = zip(*(x.split("#", 1) for x in wl))
        out["walter_logs"] = sorted({f"{r['session_id']}#{r['event_key']}" for r in conn.execute(
            """select e.session_id, e.event_key from walter_logs.events e
               join unnest(%s::text[], %s::text[]) k(s, key) on e.session_id = k.s and e.event_key = k.key
               where e.text is distinct from %s""", (list(s), list(k), MARK))})
    refs = [*ev, *dv, *ob]
    out["chunks"] = conn.execute("select count(*) n from search.chunks where ref_id = any(%s::uuid[])",
                                 (refs,)).fetchone()["n"] if refs else 0
    return out


# ── removal (shared by a purge and its re-application) ─────────────────────────────────────────────────────────────
# knowledge superseded by purged knowledge (and not purged itself)
_SUPERSEDED_BY = """status = 'superseded' and attributes->>'superseded_by' = any(%s::text[])
                    and item_id::text <> all(%s::text[])"""
_RESTORE = ("update core.derived_items set status = 'derived', valid_to = null, "
            "attributes = attributes - 'superseded_by' - 'superseded_how' where " + _SUPERSEDED_BY)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[\\"]', "", s or "")).strip().lower()


class _Matcher:
    """Exact « carries one of these quotes » test for many quotes at once (27/11/2026: a 45 000-event purge has
    25 000 quotes against 82 000 view versions, 558 M characters; testing each quote in turn never finished).
    Quotes of at least WINDOW characters are indexed by their first WINDOW characters: each text is read once,
    window by window, and only the quotes sharing a window are compared. Shorter ones (people's names) are tested
    directly. Same answers as `any(q in text for q in quotes)`."""
    WINDOW = 12

    def __init__(self, quotes: list[str]) -> None:
        self.short = [q for q in quotes if len(q) < self.WINDOW]
        self.by_head: dict[str, list[str]] = {}
        for q in quotes:
            if len(q) >= self.WINDOW:
                self.by_head.setdefault(q[:self.WINDOW], []).append(q)

    def __call__(self, text: str) -> bool:
        if any(q in text for q in self.short):
            return True
        heads, w = self.by_head, self.WINDOW
        if not heads:
            return False
        for i in range(len(text) - w + 1):
            found = heads.get(text[i:i + w])
            if found and any(text.startswith(q, i) for q in found):
                return True
        return False


_MATCHERS: dict[int, tuple[list, _Matcher]] = {}


def _quoted(text: str | None, quotes: list[str]) -> bool:
    """Whether a text carries one of the quotes (normalised once; one matcher per quote list)."""
    held = _MATCHERS.get(id(quotes))
    if held is None or held[0] is not quotes:
        if len(_MATCHERS) > 8:
            _MATCHERS.clear()
        held = _MATCHERS[id(quotes)] = (quotes, _Matcher(quotes))
    return held[1](_norm(text))


def _quotes(conn, derived: list, events: list | None = None, pattern: str | None = None) -> list[str] | None:
    """What a view would carry if it quoted the purged data: the pattern, the opening of each sentence of the purged
    knowledge and events, and the names of the people that knowledge is about (never the owner's). None when a purged
    item has no text to look for: every exposed version is then masked (the safe side)."""
    from .entities import owner_id
    out = [pattern] if pattern else []
    rows = conn.execute("select content, subject_entity_ids from core.derived_items where item_id::text = any(%s)",
                        ([str(d) for d in derived],)).fetchall()
    texts = [r["content"] for r in rows]
    if events:
        texts += [r["content"] for r in conn.execute("select content from core.events where event_id = any(%s::uuid[])",
                                                    (list(events),))]
    if any(not (x or "").strip() for x in texts[:len(rows)]):
        return None
    for x in texts:
        for s in re.split(r"(?<=[.!?…])\s+|\n+", x or "")[:50]:
            if len(s.strip()) >= 16:
                out.append(s.strip()[:40])
    me = owner_id(conn)
    ents = {str(e) for r in rows for e in (r["subject_entity_ids"] or [])} - {me}
    if ents:
        out += [r["canonical_name"] for r in conn.execute(
            "select canonical_name from core.entities where entity_id::text = any(%s) and length(canonical_name) >= 4",
            (sorted(ents),))]
    return sorted({_norm(q) for q in out if q and len(_norm(q)) >= 4})


def _exposed_versions(conn, derived: list, quotes: list[str] | None = None) -> list[tuple[str, str, int]]:
    """The view versions that quote the purged knowledge: those of a view citing it, built once it existed, whose
    text carries one of its quotes (`_quotes`). A version built before the knowledge was recorded cannot contain it,
    and one built after that never quotes it (a month view rebuilt for other days) is left untouched — incident of
    20/11: masking every version of such a view lost 695 intermediate period versions that never quoted a test item,
    and on the next test purge 130 of 192 later versions of real period views did not quote it either.
    `quotes` None (no text known) masks every version built after it."""
    rows = conn.execute(
        """select x.view_key, x.depth, x.version, x.content::text t from views.version x
           join (select e.view_key, min(d.created_at) since from views.evidence e
                 join core.derived_items d on d.item_id::text = e.ref_id::text
                 where e.ref_kind = 'derived' and e.ref_id = any(%s::text[]) group by e.view_key) s on s.view_key = x.view_key
           where x.built_at >= s.since and x.content is distinct from %s""", ([str(d) for d in derived], MARK)).fetchall()
    out = [(r["view_key"], r["depth"], r["version"]) for r in rows
           if quotes is None or _quoted(r["t"], quotes)]
    if quotes:
        since = {}
        for r in conn.execute("""select view_key, min(built_at) b from views.version
                                 where (view_key, depth, version) in (select * from unnest(%s::text[], %s::text[], %s::int[]))
                                 group by view_key""", ([e[0] for e in out], [e[1] for e in out], [e[2] for e in out])):
            since[r["view_key"]] = r["b"]
        out += _dependent_versions(conn, since, quotes, {e[0] for e in out})
    return out


def _dependent_versions(conn, since: dict, quotes: list[str], seen: set | None = None) -> list[tuple[str, str, int]]:
    """Views built on an exposed view (views.evidence ref_kind 'view': a day on its episodes, a week on its days…),
    level by level: their versions built once the cited view quoted the purged knowledge and that quote it too.
    20/11: the test café's episode was masked, but the December day, week and month that summarised it kept naming
    the test contact. Without known quotes nothing is masked here: a period summarising many views is not guessed."""
    seen, out = set(seen or ()) | set(since), []
    while since:
        rows = conn.execute(
            """select x.view_key, x.depth, x.version, x.built_at, x.content::text t from views.version x
               join (select e.view_key, min(s.b) b from views.evidence e
                     join unnest(%s::text[], %s::timestamptz[]) s(k, b) on s.k = e.ref_id::text
                     where e.ref_kind = 'view' group by e.view_key) d on d.view_key = x.view_key
               where x.built_at >= d.b and x.content is distinct from %s""",
            (list(since), list(since.values()), MARK)).fetchall()
        nxt = {}
        for r in rows:
            if r["view_key"] in seen or not _quoted(r["t"], quotes):
                continue
            out.append((r["view_key"], r["depth"], r["version"]))
            nxt[r["view_key"]] = min(nxt.get(r["view_key"], r["built_at"]), r["built_at"])
        seen |= set(nxt)
        since = nxt
    return out


def _remove(conn, t: dict) -> dict:
    """Remove the targets everywhere in the active database. The caller holds the transaction."""
    conn.execute("set local walter.purge = 'on'")
    ev, dv, ob, wl = (list(t.get(k) or []) for k in KINDS)
    n = collections.Counter()
    src_refs = []
    quotes = _quotes(conn, list(dv) + ([str(r["item_id"]) for r in conn.execute(
        "select item_id from core.derived_items where source_event_ids && %s::uuid[]", (ev,))] if ev else []),
        ev, t.get("pattern")) if (dv or ev) else None   # before the events and knowledge they come from go
    if ev:
        src_refs = [r["ref"] for r in conn.execute(
            "select source || ':' || source_id ref from core.events where event_id = any(%s::uuid[])", (ev,))]
        dv = sorted(set(dv) | {str(r["item_id"]) for r in conn.execute(
            "select item_id from core.derived_items where source_event_ids && %s::uuid[]", (ev,))})
        n["events"] = conn.execute("delete from core.events where event_id = any(%s::uuid[])", (ev,)).rowcount
        n["extraction_covered"] = conn.execute("delete from extraction.covered where event_id = any(%s::uuid[])",
                                               (ev,)).rowcount
        n["extraction_segments"] = conn.execute(
            """update extraction.segments set rejected = '[]'::jsonb,   -- its refused items may quote them
                      event_ids = array(select x from unnest(event_ids) x where x <> all(%s::uuid[]))
               where event_ids && %s::uuid[]""", (ev, ev)).rowcount
        n["triage_decisions"] = conn.execute("delete from triage.decisions where event_id = any(%s::uuid[])",
                                             (ev,)).rowcount
    if dv:
        # what the purged knowledge had replaced becomes current again: the purged statement is as if never said
        n["knowledge_restored"] = conn.execute(_RESTORE, ([str(x) for x in dv], [str(x) for x in dv])).rowcount
        exposed = _exposed_versions(conn, dv, quotes)     # before the evidence rows that tell them go
        n["views_evidence"] = conn.execute(
            "delete from views.evidence where ref_kind = 'derived' and ref_id = any(%s)", (dv,)).rowcount
        if exposed:
            n["view_versions_masked"] = conn.execute(
                """update views.version x set content = %s, stale_since = coalesce(x.stale_since, now())
                   from unnest(%s::text[], %s::text[], %s::int[]) e(view_key, depth, version)
                   where x.view_key = e.view_key and x.depth = e.depth and x.version = e.version""",
                (MARK, [e[0] for e in exposed], [e[1] for e in exposed], [e[2] for e in exposed])).rowcount
        # what was built from them (episodes, periods…) is recomputed: the publish trigger fires on insert and update
        # only, so a purge publishes each deletion itself, in the payload shape of core.publish_derived (ids, kinds
        # and dates, no text) — 20/11: a purged plan otherwise left its episode and December's periods quoting it
        n["dependents_published"] = conn.execute(
            """insert into bus.events (type, source, subject, payload)
               select 'memory.derived', 'memory', d.item_id::text,
                      jsonb_build_object('op', 'delete', 'kind', d.kind, 'derived_by', d.derived_by, 'status', 'purged',
                                         'old_status', d.status, 'epistemic', d.epistemic, 'privacy_class', d.privacy_class,
                                         'at', coalesce(d.valid_from, d.created_at), 'end', d.attributes->>'end',
                                         'owner_messages', d.attributes->>'owner_messages')
               from core.derived_items d where d.item_id = any(%s::uuid[]) and d.generation = 'g1'""", (dv,)).rowcount
        n["derived"] = conn.execute("delete from core.derived_items where item_id = any(%s::uuid[])", (dv,)).rowcount
    refs = [*ev, *dv, *ob]
    if refs:
        n["search_chunks"] = conn.execute("delete from search.chunks where ref_id = any(%s::uuid[])", (refs,)).rowcount
        # model decisions recorded from them (their outcome may quote the purged text)
        n["processing_decisions"] = conn.execute("delete from processing.decisions where refs && %s::uuid[]",
                                                 (refs,)).rowcount
        n["privacy_detections"] = conn.execute("delete from privacy.detections where target_ref = any(%s)",
                                               (refs + src_refs,)).rowcount
    if ob:
        from .objects import BUCKETS, s3
        for oid in ob:
            row = conn.execute("select storage_key, storage_zone, purged_at from core.objects where id = %s",
                               (oid,)).fetchone()
            if not row or row["purged_at"] is not None:
                continue
            try:
                s3().delete_object(Bucket=BUCKETS[row["storage_zone"]], Key=row["storage_key"])
            except Exception as e:  # noqa: BLE001 — bytes already gone (re-application): the registry is still marked
                n["object_bytes_errors"] += 1
                print(f"purge: object bytes not deleted ({type(e).__name__})")
            conn.execute("""update core.objects set purged_at = now(), derived_text = null, original_name = null,
                                meta = '{}', source_ref = '{}' where id = %s""", (oid,))
            n["objects"] += 1
    if wl:
        s, k = (list(x) for x in zip(*(x.split("#", 1) for x in wl)))
        n["walter_logs_masked"] = conn.execute(
            """update walter_logs.events e set text = %s, data = '{}'::jsonb, chars = length(%s)
               from unnest(%s::text[], %s::text[]) x(s, key)
               where e.session_id = x.s and e.event_key = x.key and e.text is distinct from %s""",
            (MARK, MARK, s, k, MARK)).rowcount
    t["derived"] = dv
    return dict(n)


def _record_ledger(conn, pid: int, targets: dict, reason: str) -> None:
    with conn.cursor() as cur:
        cur.executemany("""insert into system.purge_ledger (purge_id, kind, target) values (%s, %s, %s)
                           on conflict (kind, target) do nothing""",
                        [(pid, k, x) for k in KINDS for x in targets.get(k) or ()])
    # the instance copy is written before the commit: a line whose purge rolled back is harmless (reapply finds
    # nothing), a committed purge without its line could be undone by a restore
    at = datetime.now(timezone.utc).isoformat()
    for k in KINDS:
        if targets.get(k):
            ledger_append({"purge_id": pid, "at": at, "kind": k, "targets": list(targets[k]),
                           "reason_sha256": hashlib.sha256(reason.encode()).hexdigest()})


def purge(*, reason: str, requested_by: str, event_ids=None, object_refs=None, pattern=None, sessions=None,
          derived_ids=None, execute=False, rotate_local_dumps=False) -> dict:
    with connect() as conn:
        targets = select_targets(conn, event_ids=event_ids, object_refs=object_refs, pattern=pattern, sessions=sessions,
                                 derived_ids=derived_ids)
        selector = {"event_ids": len(event_ids or []), "object_refs": len(object_refs or []),
                    "sessions": len(sessions or []), "derived_ids": len(derived_ids or []),
                    "pattern_sha256": hashlib.sha256(pattern.encode()).hexdigest() if pattern else None}
        if not execute:
            counts = {COUNT_KEYS[k]: len(v) for k, v in targets.items()}
            if targets["derived"]:    # the view versions that may quote that knowledge are masked: say how many
                exposed = _exposed_versions(conn, targets["derived"], _quotes(conn, targets["derived"], targets["event"],
                                                                               pattern))
                counts["views_masked"] = len({e[0] for e in exposed})
                counts["view_versions_masked"] = len(exposed)
                counts["knowledge_restored"] = conn.execute(   # replaced by the purged knowledge: current again
                    "select count(*) n from core.derived_items where " + _SUPERSEDED_BY,
                    ([str(x) for x in targets["derived"]],) * 2).fetchone()["n"]
            conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status)
                            values (%s,%s,%s,%s,%s,'dry_run')""",
                         (requested_by, reason, json.dumps(selector),
                          _fp([x for k in KINDS for x in targets[k]]), json.dumps(counts)))
            return {"status": "dry_run", "counts": counts}
        removed = _remove(conn, {**targets, "pattern": pattern})
        counts = {COUNT_KEYS[k]: len(v) for k, v in targets.items()}
        pid = conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status,
                                  backups_rewritten) values (%s,%s,%s,%s,%s,'executed',false) returning purge_id""",
                           (requested_by, reason, json.dumps(selector), _fp([x for k in KINDS for x in targets[k]]),
                            json.dumps({**counts, "removed": removed}))).fetchone()["purge_id"]
        _record_ledger(conn, pid, targets, reason)
    if targets["object"]:
        # S3 deletes through rclone land in Drive's trash: empty it (drive.file scope = only W.Alter's own files)
        subprocess.run(["rclone", "cleanup", "gdrive:"], check=False)
    out = {"status": "executed", "purge_id": pid, "counts": counts, "removed": removed, "backups": exposure()}
    if rotate_local_dumps:
        out["rotated_local_dumps"] = _rotate_local_dumps()
    return out


def reapply(*, requested_by: str, execute: bool = False) -> dict:
    """Re-apply every ledger entry to the current database (after a restore). Dry run unless execute."""
    with connect() as conn:
        led = ledger(conn)
        found = present(conn, led)
        ops = sorted(led.get("operation", ()))
        out = {"present": {k: (len(v) if isinstance(v, list) else v) for k, v in found.items()}, "operations": ops}
        if not execute:
            out["status"] = "dry_run"
            return out
        removed = _remove(conn, {k: found[k] for k in KINDS}) if any(found[k] for k in KINDS) else {}
        refs = [x for k in ("event", "derived", "object") for x in sorted(led.get(k, ()))]
        if refs:   # chunks rebuilt from an older dump even when their sources are already gone
            removed["search_chunks_left"] = conn.execute("delete from search.chunks where ref_id = any(%s::uuid[])",
                                                         (refs,)).rowcount
        pid = conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status,
                                  backups_rewritten) values (%s, 'reapply the purge ledger', %s, %s, %s, 'executed', false)
                              returning purge_id""",
                           (requested_by, json.dumps({"operation": "purge.reapply"}), [],
                            json.dumps({"present": out["present"], "removed": removed}))).fetchone()["purge_id"]
        with conn.cursor() as cur:           # the database ledger again holds every entry of the instance file
            cur.executemany("""insert into system.purge_ledger (purge_id, kind, target) values (%s, %s, %s)
                               on conflict (kind, target) do nothing""",
                            [(pid, k, x) for k in (*KINDS, "operation") for x in sorted(led.get(k, ()))])
    out["removed"] = removed
    from . import observability
    if observability.OPERATION in ops:
        r = observability.retire(requested_by=requested_by, reason="reapply the purge ledger", execute=True)
        out["observability.retire"] = {k: r.get(k) for k in ("status", "removable", "purge_id")}
    out["status"] = "executed"
    return out


def verify() -> dict:
    """Cheap check (health): purged targets present again, retired observability rows above what was kept."""
    from .observability import OPERATION, RETIRED_TYPES
    with connect() as conn:
        led = ledger(conn)
        found = present(conn, led)
        out = {"ledger": {k: len(v) for k, v in led.items()},
               "present_again": {k: (len(v) if isinstance(v, list) else v) for k, v in found.items()}}
        if OPERATION in led.get("operation", ()):
            row = conn.execute("""select counts from system.purges where selector->>'operation' = %s
                                  and status = 'executed' order by purge_id desc limit 1""", (OPERATION,)).fetchone()
            kept = sum((row["counts"].get("kept") or {}).values()) if row else None
            now = conn.execute("select count(*) n from core.events where event_type = any(%s)",
                               (list(RETIRED_TYPES),)).fetchone()["n"]
            out["observability"] = {"kept_at_retirement": kept, "now": now}
            if kept is None or now > kept:
                out["present_again"]["observability_events"] = now - (kept or 0)
    out["ok"] = not any(out["present_again"].values())
    return out


# ── backups ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _env(kind: str) -> dict:
    try:
        txt = subprocess.run(["walter-ops", "backup", "env", kind], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out = {}
    for line in txt.splitlines():
        if line.startswith("export ") and "=" in line:
            k, v = line[7:].split("=", 1)
            if "PASSWORD" not in k:
                out[k] = v.strip("'\"")
    return out


def exposure() -> list[dict]:
    """Where purged data may still exist outside the active database, and for how long. Read-only."""
    out = []
    pg = _env("pg")
    if pg.get("WALTER_BACKUP_DIR"):
        d = Path(pg["WALTER_BACKUP_DIR"])
        dumps = sorted(d.glob("*" + pg.get("WALTER_BACKUP_SUFFIX", ".dump"))) if d.exists() else []
        out.append({"where": str(d), "what": "nightly PostgreSQL dumps (rolling)", "count": len(dumps),
                    "kept": f"{pg.get('WALTER_BACKUP_KEEP_DAILY', '?')} daily + "
                            f"{pg.get('WALTER_BACKUP_KEEP_WEEKLY', '?')} weekly",
                    "until": "about 5 weeks after the purge, by rotation", "automatic_change": False,
                    "definitive": "purge --rotate-local-dumps (fresh dump, then the older ones are shredded)"})
    sd = _env("statedb")
    if sd.get("WALTER_BACKUP_DIR"):
        out.append({"where": sd["WALTER_BACKUP_DIR"], "what": "Hermes state.db copies (conversations)",
                    "kept": f"{sd.get('WALTER_BACKUP_KEEP', '?')} nightly",
                    "until": "3 nights after state.db itself is redacted", "automatic_change": False,
                    "definitive": "redact state.db (RUNBOOK § Purge), then rotation"})
    rs = _env("restic")
    if rs.get("WALTER_RESTIC_REPOSITORY"):
        out.append({"where": rs["WALTER_RESTIC_REPOSITORY"], "what": "restic snapshots (instance folders, pg dump)",
                    "kept": f"{rs.get('WALTER_OFFSITE_KEEP_DAILY', '?')}d/{rs.get('WALTER_OFFSITE_KEEP_WEEKLY', '?')}w/"
                            f"{rs.get('WALTER_OFFSITE_KEEP_MONTHLY', '?')}m; snapshots tagged keep are never forgotten",
                    "until": "up to 12 months for rolling snapshots; keep snapshots until Monsieur decides",
                    "automatic_change": False,
                    "definitive": "manual: restic rewrite --exclude of the files holding it, then forget --prune"})
    inst = _instance()
    for sub, what in (("backups/memory-archive", "encrypted phase archives (keep)"),
                      ("backups/changes", "restore points of changes (encrypted targeted dumps)")):
        if inst and (inst / sub).exists():
            out.append({"where": str(inst / sub), "what": what, "until": "until Monsieur decides",
                        "automatic_change": False,
                        "definitive": "manual, per archive (RUNBOOK § Purge); the ledger re-applies on restore"})
    out.append({"where": "gdrive:W.Alter Backups/pg (age archives; job disabled 2026-11-01)",
                "what": "retired offsite dumps", "until": "until deleted by hand", "automatic_change": False,
                "definitive": "manual rclone deletefile (RUNBOOK § Purge)"})
    out.append({"where": "Raw Vault, secure bucket: raw Hermes exports", "what": "daily raw state.db rows",
                "until": "kept", "automatic_change": False, "definitive": "manual (RUNBOOK § Purge)"})
    return out


def _rotate_local_dumps() -> dict:
    """Explicit only: fresh dump, then shred the older ROLLING local dumps. Never restic, keep, archives, changes."""
    pg = _env("pg")
    d = Path(pg.get("WALTER_BACKUP_DIR") or "")
    if not pg.get("WALTER_BACKUP_DIR") or not d.is_dir():
        return {"status": "pg backup directory unknown: nothing rotated"}
    subprocess.run(["systemctl", "start", "walter-pg-backup"], check=True)
    dumps = sorted(d.glob("*" + pg.get("WALTER_BACKUP_SUFFIX", ".dump")), key=lambda p: p.stat().st_mtime)
    if not dumps:
        return {"status": "no dump"}
    for p in dumps[:-1]:
        subprocess.run(["shred", "-u", str(p)], check=False)
    return {"status": "rotated", "kept": dumps[-1].name, "shredded": len(dumps) - 1}
