"""Read agent sessions (slice by slice, from walter-memory's digest) and decisions (against the 40 before them)
with the model poste, and turn the answers into cards and replacement links. Each slice is applied in its own
transaction, then the session's read position moves; a pause keeps the position for the next pass."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import cards, llm
from .config import Config

PROMPTS = Path(__file__).resolve().parent / "prompts"
LABEL = {"waiting_owner": "attend le propriétaire", "in_progress": "en cours", "paused": "en pause",
         "done": "fini", "abandoned": "abandonné"}
KIND = {"user": "propriétaire", "assistant": "agent", "file": "fichier", "compaction": "résumé"}
NULL_STR = {"type": ["string", "null"]}
SESSION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["is_walter_development", "cards", "approvals"],
    "properties": {
        "is_walter_development": {"type": "boolean"},
        "cards": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "title", "module", "status", "owner", "change", "deadline", "decisions", "files",
                         "blocks", "evidence"],
            "properties": {
                "ref": NULL_STR, "title": {"type": "string"}, "module": NULL_STR,
                "status": {"type": "string", "enum": list(cards.STATUSES)},
                "owner": {"type": "string", "enum": list(cards.OWNERS)},
                "change": {"type": "string"}, "deadline": NULL_STR,
                "decisions": {"type": "array", "items": {"type": "string"}},
                "files": {"type": "array", "items": {"type": "string"}},
                "blocks": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["seq", "quote"],
                    "properties": {"seq": {"type": "integer"}, "quote": {"type": "string"}}}}}}},
        "approvals": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["ref", "seq", "quote"],
            "properties": {"ref": {"type": "string"}, "seq": {"type": "integer"}, "quote": {"type": "string"}}}}}}
DECISION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["succeeds"],
    "properties": {"succeeds": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["anchor", "quote"],
        "properties": {"anchor": {"type": "string"}, "quote": {"type": "string"}}}}}}


def _digest(session_id: str, after: int) -> dict:
    out = subprocess.run(["walter-memory", "logs", "digest", session_id, "--after-seq", str(after), "--cloud-safe",
                          "--json"], capture_output=True, text=True, check=True, timeout=120).stdout
    return json.loads(out)


def _when(text) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text)) if text else None
    except ValueError:
        return None


def _session_prompt(conn, d: dict) -> list[dict]:
    decisions = conn.execute("""select anchor, date, title from devboard.decisions where removed_at is null
                                order by date desc, id desc limit 60""").fetchall()
    system = (PROMPTS / "session.md").read_text().replace("{modules}", ", ".join(sorted(cards.known_modules()))) \
        .replace("{decisions}", "\n".join(f"{r['anchor']} · {r['date']} · {r['title']}" for r in decisions) or "(aucune)")
    known = conn.execute("""select ref, title, module, status from devboard.cards
                            where status not in ('done', 'abandoned') or updated_at > now() - interval '14 days'
                            order by last_activity_at desc limit 150""").fetchall()
    s = d.get("session") or {}
    lines = [f"Chantiers déjà connus (réutilise le numéro si c'est le même) :"]
    lines += [f"{r['ref']} · {r['module'] or '—'} · {LABEL[r['status']]} · {r['title']}" for r in known] or ["(aucun)"]
    lines += ["", f"Session {s.get('runtime', '?')} « {s.get('title') or 'sans titre'} », "
                  f"événements {d['from_seq']} à {d['to_seq']} :"]
    lines += [f"[{i['seq']}] {KIND.get(i['kind'], i['kind'])} : {i['text']}" for i in d["items"]]
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n".join(lines)}]


def _upsert_session(conn, session_id: str, s: dict) -> None:
    conn.execute("""insert into devboard.sessions (session_id, runtime, title, cwd) values (%s, %s, %s, %s)
                    on conflict (session_id) do update set title = coalesce(excluded.title, devboard.sessions.title),
                      cwd = coalesce(excluded.cwd, devboard.sessions.cwd)""",
                 (session_id, s.get("runtime") or session_id.split("/", 1)[0], s.get("title"), s.get("cwd")))


def _set(conn, session_id: str, **cols) -> None:
    sets = ", ".join(f"{k} = %({k})s" for k in cols)
    conn.execute(f"update devboard.sessions set {sets} where session_id = %(sid)s", {**cols, "sid": session_id})


def read_session(cfg: Config, conn, session_id: str) -> str:
    row = conn.execute("select read_seq from devboard.sessions where session_id = %s", (session_id,)).fetchone()
    pos = row["read_seq"] if row else 0
    dev = read = False
    while True:
        d = _digest(session_id, pos)
        _upsert_session(conn, session_id, d.get("session") or {})
        if not d["items"]:
            if d.get("to_seq") and d["to_seq"] > pos:
                pos = d["to_seq"]
                _set(conn, session_id, read_seq=pos)
            if not d.get("more"):
                break
            continue
        lo, hi = d["from_seq"], d["to_seq"]
        k = llm.key("session", session_id, lo, hi)
        try:
            with conn.transaction():
                result = llm.read(cfg, conn, key=k, kind="session", source_ref=session_id, from_seq=lo, to_seq=hi,
                                  prompt=_session_prompt(conn, d), schema=SESSION_SCHEMA,
                                  validate=lambda r: cards.validate(conn, r, lo, hi))
                if result is not None:
                    if result.get("is_walter_development"):
                        dev = True
                        cards.apply(conn, session_id, lo, hi, result, at=_when(d["items"][-1].get("at")))
                    read = True
                    _set(conn, session_id, read_seq=hi)
        except llm.Paused:
            _set(conn, session_id, state="paused")
            return "paused"
        if result is None:
            failed = conn.execute("select attempts from devboard.readings where key = %s", (k,)).fetchone()
            if failed and failed["attempts"] >= llm.MAX_ATTEMPTS:
                _set(conn, session_id, read_seq=hi)    # given up on this slice: never block the session behind it
            _set(conn, session_id, state="failed")
            return "failed"
        pos = hi
        if not d.get("more"):
            break
    state = "done" if dev or not read else "skipped"
    _set(conn, session_id, state=state, dirty=False)
    return state


def read_decision(cfg: Config, conn, decision_id: int) -> str:
    d = conn.execute("""select d.*, s.body from devboard.decisions d
                        left join devboard.sections s on s.doc_path = d.doc_path and s.anchor = d.anchor
                        where d.id = %s""", (decision_id,)).fetchone()
    if d is None:
        return "failed"
    prev = conn.execute("""select d.id, d.anchor, d.date, d.title, s.body from devboard.decisions d
                           left join devboard.sections s on s.doc_path = d.doc_path and s.anchor = d.anchor
                           where d.removed_at is null and (d.date, d.id) < (%s, %s)
                           order by d.date desc, d.id desc limit 40""", (d["date"], d["id"])).fetchall()
    if not prev:
        conn.execute("update devboard.decisions set read_sha256 = sha256 where id = %s", (decision_id,))
        return "done"
    ids = {r["anchor"]: r["id"] for r in prev}

    def validate(r):
        for s in r.get("succeeds") or []:
            if s.get("anchor") not in ids:
                raise ValueError(f"unknown decision anchor {s.get('anchor')}")
            if not (s.get("quote") or "").strip():
                raise ValueError(f"replacement of {s['anchor']} without quote")

    listing = "\n".join(f"- {r['anchor']} · {r['date']} · {r['title']} — {(r['body'] or '')[:300]}" for r in prev)
    prompt = [{"role": "system", "content": (PROMPTS / "decision.md").read_text()},
              {"role": "user", "content": f"Nouvelle décision ({d['date']}, ancre {d['anchor']}) :\n"
                                          f"{(d['body'] or d['title'])[:6000]}\n\nDécisions précédentes :\n{listing}"}]
    try:
        with conn.transaction():
            result = llm.read(cfg, conn, key=llm.key("decision", f"{d['anchor']}@{d['sha256'][:12]}", None, None),
                              kind="decision", source_ref=d["anchor"], from_seq=None, to_seq=None, prompt=prompt,
                              schema=DECISION_SCHEMA, validate=validate)
            if result is not None:
                conn.execute("delete from devboard.decision_links where newer_id = %s", (decision_id,))
                for s in result.get("succeeds") or []:
                    conn.execute("""insert into devboard.decision_links (newer_id, older_id, quote)
                                    values (%s, %s, %s) on conflict do nothing""",
                                 (decision_id, ids[s["anchor"]], s["quote"].strip()[:400]))
                conn.execute("update devboard.decisions set read_sha256 = sha256 where id = %s", (decision_id,))
    except llm.Paused:
        return "paused"
    return "done" if result is not None else "failed"
