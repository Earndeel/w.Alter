"""The owner's two buttons (2026-11-15): « Abandonner » (the card leaves the board, with his reason) and « Reprendre »
(Walter Engine takes the chantier up again). A resume is one turn of the card's own engine conversation
(`web/<account>/devboard-w-<n>`, web door = the owner's full access, visible in Walter Web), briefed with what the
board knows of the card; it is followed here until the turn ends, then the card takes the outcome the engine states
in its last line. The board never runs the work itself and never answers an approval for the owner."""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import correct, db

BY = "walter-reprise"                     # author of the corrections a resume makes (never « owner »)
OUTCOMES = ("done", "waiting_owner", "in_progress", "abandoned")
RESUMABLE = ("waiting_owner", "in_progress", "paused", "done", "abandoned")
OUTCOME_LINE = re.compile(r"^\W*(?:ÉTAT|ETAT|STATE)\s*[:=]\s*`?(done|waiting_owner|in_progress|abandoned)`?\W*$",
                          re.I | re.M)
ENDED = {"ok", "cancelled", "budget_exhausted", "error", "interrupted", "unknown_outcome"}
STATUS_FR = {"waiting_owner": "attend {owner}", "in_progress": "en cours", "paused": "en pause", "done": "fini",
             "abandoned": "abandonné"}


class ActionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Engine:
    """Engine API client (core/interfaces/api): loopback, token in the header, never in the URL."""

    def __init__(self, url: str, token_file: Path):
        self.url, self.token_file = url.rstrip("/"), token_file

    def op(self, body: dict, timeout: float = 30) -> dict:
        token = self.token_file.read_text().strip()
        req = urllib.request.Request(self.url + "/v1", data=json.dumps({"version": 1, **body}).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                err = json.load(e)
            except ValueError:
                err = {}
            raise ActionError(502, f"moteur : {err.get('error') or e.code} {err.get('detail') or ''}".strip()) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError):
            raise ActionError(503, "le moteur Walter ne répond pas") from None


def conversation(ref: str) -> str:
    return "devboard-" + ref.lower()


def _card(conn, ref: str) -> dict:
    card = conn.execute("select * from devboard.cards where ref = %s", (ref,)).fetchone()
    if card is None:
        raise ActionError(404, f"carte inconnue {ref}")
    return card


def _line(text: str | None, n: int = 400) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _cli(*args: str, timeout: float = 12) -> dict | None:
    """One walter-memory reading (its declared CLI, cloud-safe); None when it cannot answer: the brief goes without."""
    try:
        out = subprocess.run(["walter-memory", *args], capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _status(status: str, owner: str) -> str:
    return STATUS_FR.get(status, status).replace("{owner}", owner)


def _where_it_stopped(ev: list[dict], owner: str) -> list[str]:
    """The most recent session evidence in full: the agent's message it was read from and the owner's request before
    it, read from walter-logs. Never what followed: a long session moves on to other work (16/11: the steps after a
    card's last evidence were about something else entirely)."""
    last = next((e for e in ev if e["kind"] == "session" and e["seq"] is not None), None)
    if not last:
        return []
    d = _cli("logs", "timeline", last["source_ref"], "--seq", str(last["seq"]), "--before", "60", "--after", "0",
             "--max-chars", "1500", "--cloud-safe", "--json")
    if not d:
        return []
    s = d.get("session") or {}
    events = [e for e in d.get("events") or [] if (e.get("seq") or 0) <= last["seq"]]
    said = [e for e in events if e.get("type") == "assistant/message" and (e.get("text") or "").strip()]
    asked = [e for e in events if e.get("type") == "user/message" and (e.get("text") or "").strip()]
    out = ["", f"Dernier point connu du chantier (session {last['source_ref']}, « {_line(s.get('title'), 120) or '—'} », "
               f"dossier {s.get('cwd') or '?'}, jusqu'à #{last['seq']}) :"]
    if asked:
        out.append(f"- demande de {owner} juste avant (#{asked[-1].get('seq')}) : « {_line(asked[-1]['text'], 400)} »")
    if said:
        out.append(f"- compte rendu de l'agent (#{said[-1].get('seq')}) : « {_line(said[-1]['text'], 1200)} »")
    return out if len(out) > 2 else []


def _tasks(ev: list[dict]) -> list[str]:
    """The owner's durable tasks the card was read from (walter-memory tasks): status, progress, thread."""
    out = []
    for tid in dict.fromkeys(e["source_ref"].removeprefix("task:") for e in ev if e["kind"] == "task"):
        t = _cli("tasks", "show", tid)
        t = (t or {}).get("task", t) if isinstance(t, dict) else None
        if not t:
            continue
        prog = t.get("progress") or {}
        bits = [f"- tâche {tid[:8]} ({t.get('status')}, fil {t.get('thread_id') or '—'}) : {_line(t.get('goal'), 200)}"]
        for key, label in (("done", "fait"), ("next", "suite prévue"), ("blocked", "bloqué")):
            items = prog.get(key) if isinstance(prog, dict) else None
            if items:
                bits.append(f"  {label} : " + " ; ".join(_line(i, 200) for i in list(items)[-3:]))
        out += bits
    return (["", "Tâches durables liées dans la mémoire (walter-memory tasks) :"] + out) if out else []


def brief(conn, ref: str, note: str = "", owner: str = "le propriétaire") -> str:
    """The engine's instructions for resuming one card: everything the board knows of it, and how to end. `owner` =
    how the instance names its owner (settings `owner_name`): the software itself never names a person."""
    c = _card(conn, ref)
    ev = conn.execute("""select kind, source_ref, seq, quote, at from devboard.card_evidence where card_id = %s
                         order by at desc, id desc limit 12""", (c["id"],)).fetchall()
    act = conn.execute("""select at, text from devboard.activity where card_id = %s
                          order by at desc, id desc limit 12""", (c["id"],)).fetchall()
    corr = conn.execute("""select field, value, reason, by, at from devboard.corrections where card_id = %s
                           order by at desc limit 10""", (c["id"],)).fetchall()
    links = conn.execute("select kind, target from devboard.card_links where card_id = %s order by kind, target",
                         (c["id"],)).fetchall()
    anchors = [l["target"] for l in links if l["kind"] == "decision"]
    decs = conn.execute("""select anchor, date, title, doc_path from devboard.decisions where anchor = any(%s)""",
                        (anchors,)).fetchall() if anchors else []
    blocks = [l["target"] for l in links if l["kind"] == "blocks"]
    blocked_by = conn.execute("""select c.ref, c.title, c.status from devboard.card_links l join devboard.cards c
                                 on c.id = l.card_id where l.kind = 'blocks' and l.target = %s""", (ref,)).fetchall()
    prev = conn.execute("""select started_at, status, outcome, summary from devboard.resumes where card_id = %s
                           and status <> 'running' order by started_at desc limit 1""", (c["id"],)).fetchone()
    d = lambda t: t.astimezone(timezone.utc).strftime("%d/%m %H:%M") if t else "?"
    out = [f"Reprise du chantier {ref} du tableau de développement de Walter, demandée par {owner} (bouton « Reprendre », "
           f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC).", "",
           f"Titre : {c['title']}",
           f"Module : {c['module'] or '—'}",
           f"État sur le tableau avant la reprise : {_status(c['status'], owner)}",
           f"Porteur : {c['owner'] or '—'}" + (f" · échéance {c['deadline']}" if c["deadline"] else ""),
           f"Ce que ça change : {_line(c['change'], 1200) or '—'}", "",
           f"Consigne de {owner} avec ce clic : " + (note.strip() or "(aucune, reprends là où le travail s'est arrêté)")]
    if prev:
        out += ["", f"Reprise précédente ({d(prev['started_at'])}, {prev['status']}, issue {prev['outcome'] or '—'}) : "
                    + _line(prev["summary"], 800)]
    if corr:
        out += ["", f"Corrections de {owner} ou des reprises (la plus récente d'abord) :"]
        out += [f"- {d(k['at'])} {k['field']} → {json.dumps(k['value'], ensure_ascii=False)}"
                + (f" ({_line(k['reason'], 300)})" if k["reason"] else "") + f" [par {k['by']}]" for k in corr]
    if decs:
        out += ["", "Décisions liées :"] + [f"- {k['date']} {k['title']} ({k['doc_path']}#{k['anchor']})" for k in decs]
    files = [l["target"] for l in links if l["kind"] == "file"]
    if files:
        out += ["", "Fichiers (un chemin relatif part du dossier de sa session d'origine ; un module a pu changer de "
                    "place depuis : `walter path <module>`) : " + ", ".join(files[:20])]
    if blocks or blocked_by:
        out += ["", "Bloque : " + (", ".join(blocks) or "—") + " · bloqué par : "
                + (", ".join(f"{b['ref']} ({_status(b['status'], owner)})" for b in blocked_by) or "—")]
    out += _where_it_stopped(ev, owner) + _tasks(ev)
    if ev:
        seen, uniq = set(), []
        for e in ev:                                   # the same words read in several sessions: shown once
            if _line(e["quote"], 300) not in seen:
                seen.add(_line(e["quote"], 300))
                uniq.append(e)
        out += ["", "Preuves (souvenirs datés : vérifie avant d'affirmer ; ouvre une session avec l'outil "
                    "logs_timeline(session, seq), une tâche avec tasks_list) :"]
        out += [f"- {d(e['at'])} {e['kind']} {e['source_ref']}{'#' + str(e['seq']) if e['seq'] is not None else ''} : "
                f"« {_line(e['quote'], 300)} »" for e in uniq]
    if act:
        out += ["", "Activité récente sur la carte :"] + [f"- {d(a['at'])} {_line(a['text'], 300)}" for a in act]
    out += ["", "Comment travailler :",
            "1. Vérifie d'abord l'état réel (fichiers, services, git, journaux) : le travail est peut-être déjà fait, "
            "à moitié fait, ou devenu inutile. Les preuves ci-dessus sont des souvenirs datés, pas l'état présent.",
            "2. Fais ce qui reste, avec les règles habituelles (sauvegarde avant de modifier, pas de secret affiché).",
            f"3. Arrête-toi et demande à {owner} au lieu d'agir pour : un lot du moteur (son accord explicite), un choix "
            "d'architecture, de données, de budget ou de vie privée, une suppression irréversible, tout message envoyé "
            "en son nom (il le relit avant l'envoi).",
            "4. Termine par un compte rendu court en français simple : ce qui est fait et vérifié, ce qui reste, ce que "
            f"{owner} doit décider. Puis, seule sur la dernière ligne, l'état de la carte :",
            f"ÉTAT: done (fini et vérifié) | waiting_owner (il faut une décision ou une action de {owner}) | "
            "in_progress (reste du travail pour Walter) | abandoned (plus d'actualité, dis pourquoi)"]
    return "\n".join(out)


def running(conn, card_id: int) -> dict | None:
    return conn.execute("select * from devboard.resumes where card_id = %s and status = 'running'",
                        (card_id,)).fetchone()


def resume(conn, cfg, engine: Engine, ref: str, note: str = "") -> dict:
    """Start the resume of one card: open (or find) its engine conversation, submit the brief, record it."""
    note = str(note or "").strip()[:2000]
    c = _card(conn, ref)
    if c["status"] not in RESUMABLE:
        raise ActionError(409, f"statut {c['status']}")
    if running(conn, c["id"]):
        raise ActionError(409, f"{ref} est déjà en cours de reprise")
    text = brief(conn, ref, note, cfg.owner_name)
    opened = engine.op({"op": "session.open", "interface": cfg.engine_interface, "conversation": conversation(ref),
                        "principal": {"kind": "owner", "id": cfg.engine_account}, "mode": "interactive",
                        **({"level": cfg.resume_level} if cfg.resume_level else {})})
    sid = opened["session_id"]
    n = conn.execute("select count(*) n from devboard.resumes where card_id = %s", (c["id"],)).fetchone()["n"] + 1
    request_id = f"devboard-{ref.lower()}-r{n}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    sub = engine.op({"op": "turn.submit", "session_id": sid, "message": {"text": text}, "channel": "owner",
                     "idempotency_key": request_id})
    walter_session = sub.get("walter_session") or opened.get("walter_session")
    rid = conn.execute("""insert into devboard.resumes (card_id, session_id, walter_session, request_id, note,
                                                        status_before)
                          values (%s, %s, %s, %s, %s, %s) returning id""",
                       (c["id"], sid, walter_session, request_id, note or None, c["status"])).fetchone()["id"]
    if c["status"] != "in_progress":
        correct.correct(conn, {"ref": ref, "field": "status", "value": "in_progress", "by": "owner",
                               "reason": f"repris par {cfg.owner_name} (bouton « Reprendre »)" + (f" : {note}" if note else "")})
    conn.execute("""insert into devboard.activity (kind, source_ref, card_id, text) values ('resume', %s, %s, %s)""",
                 (f"resume:{rid}", c["id"], f"{ref} repris par Walter à la demande de {cfg.owner_name}"
                  + (f" (« {_line(note, 200)} »)" if note else "")))
    conn.execute("""insert into devboard.live (session_id, runtime, title, card_id, at) values (%s, 'engine', %s, %s, now())
                    on conflict (session_id) do update set at = now(), card_id = excluded.card_id, title = excluded.title""",
                 (walter_session or sid, f"Reprise de {ref}", c["id"]))
    db.notify(conn, "cards", refs=[ref])
    return {"ok": True, "ref": ref, "resume": rid, "session_id": sid, "walter_session": walter_session,
            "request_id": request_id}


def abandon(conn, engine: Engine | None, ref: str, reason: str = "") -> dict:
    """The card leaves the board (status abandoned, his reason); a running resume of it is interrupted first."""
    reason = str(reason or "").strip()[:500]
    c = _card(conn, ref)
    r = running(conn, c["id"])
    if r and engine is not None:
        try:
            engine.op({"op": "turn.cancel", "session_id": r["session_id"], "reason": "chantier abandonné par le propriétaire"})
        except ActionError:
            pass                       # the turn may already have ended; the follower records what it became
    out = correct.correct(conn, {"ref": ref, "field": "status", "value": "abandoned", "by": "owner",
                                 "reason": reason or "abandonné par le propriétaire (bouton « Abandonner »)"})
    return {**out, "cancelled_resume": r["id"] if r else None}


def outcome_of(text: str) -> str | None:
    found = OUTCOME_LINE.findall(text or "")
    return found[-1].lower() if found else None


def _summary(text: str) -> str:
    body = OUTCOME_LINE.sub("", text or "").strip()
    return body[:4000]


def _notify(cfg, text: str) -> None:
    if not cfg.notify_command:
        return
    try:
        r = subprocess.run([*cfg.notify_command, text], capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
        detail = (r.stdout or r.stderr).strip()[-200:]
    except (OSError, subprocess.SubprocessError) as e:
        ok, detail = False, type(e).__name__
    print(f"walter-devboard: end-of-resume note {'sent' if ok else 'NOT sent'} ({detail})", file=sys.stderr, flush=True)


def finish(conn, cfg, row: dict, result: dict) -> dict:
    """Record the end of one resume and give the card the outcome the engine stated (nothing when it stated none)."""
    status = result.get("status") if result.get("status") in ENDED | {"lost"} else "unknown_outcome"
    text = str(result.get("text") or "")
    outcome = outcome_of(text) if status == "ok" else None
    card = conn.execute("select * from devboard.cards where id = %s", (row["card_id"],)).fetchone()
    conn.execute("""update devboard.resumes set status = %s, outcome = %s, summary = %s, ended_at = now()
                    where id = %s""", (status, outcome, _summary(text) or None, row["id"]))
    conn.execute("delete from devboard.live where session_id = %s", (row["walter_session"] or row["session_id"],))
    ref = card["ref"]
    abandoned_meanwhile = card["status"] == "abandoned" and outcome != "abandoned"
    if outcome and not abandoned_meanwhile and outcome != card["status"]:
        correct.correct(conn, {"ref": ref, "field": "status", "value": outcome, "by": BY,
                               "reason": "issue de la reprise : " + _line(_summary(text), 300)})
    label = {"ok": "terminée", "cancelled": "interrompue", "budget_exhausted": "arrêtée (plafond)",
             "error": "en erreur", "interrupted": "coupée (moteur arrêté)", "unknown_outcome": "sans issue connue",
             "lost": "perdue"}.get(status, status)
    conn.execute("""insert into devboard.activity (kind, source_ref, card_id, text) values ('resume', %s, %s, %s)
                    on conflict do nothing""",
                 (f"resume-end:{row['id']}", card["id"], f"{ref} : reprise {label}"
                  + (f", carte → {_status(outcome, cfg.owner_name)}" if outcome else "")
                  + (f" — {_line(_summary(text), 240)}" if text else "")))
    db.notify(conn, "cards", refs=[ref])
    if not abandoned_meanwhile:
        head = f"Tableau · {ref} « {_line(card['title'], 80)} » : reprise {label}"
        head += f", carte {_status(outcome, cfg.owner_name)}." if outcome else "."
        _notify(cfg, head + ("\n\n" + _line(_summary(text), 900) if text else ""))
    return {"ref": ref, "status": status, "outcome": outcome}


def follow_once(cfg, engine: Engine) -> list[dict]:
    """One pass over the running resumes: those whose turn ended are recorded. Never raises."""
    done = []
    try:
        with db.autocommit() as conn:
            rows = conn.execute("select * from devboard.resumes where status = 'running' order by id").fetchall()
            for row in rows:
                age_h = (datetime.now(timezone.utc) - row["started_at"]).total_seconds() / 3600
                try:
                    res = engine.op({"op": "turn.result", "session_id": row["session_id"],
                                     "request_id": row["request_id"]}, timeout=20).get("result") or {}
                except ActionError:
                    res = {}
                if res.get("done"):
                    with conn.transaction():
                        done.append(finish(conn, cfg, row, res))
                elif age_h >= cfg.resume_lost_hours:
                    with conn.transaction():
                        done.append(finish(conn, cfg, row, {"status": "lost", "text": res.get("text") or ""}))
                else:
                    conn.execute("update devboard.live set at = now() where session_id = %s",
                                 (row["walter_session"] or row["session_id"],))
    except Exception:            # the follower outlives a database or engine hiccup; the next pass retries
        return done
    return done
