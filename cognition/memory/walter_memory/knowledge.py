"""Knowledge consolidation: reconciliation and the single write gate (lot 1 of the organic loop, 2026-11-19).

Why. Extraction used to append: each segment's model said itself whether a statement restated, replaced or
contradicted a known item, and anything else became one more item (1 690 goals « requested », 25 closed, 0 verified).
Memory now *updates*: every statement extracted from a conversation (extract2) is reconciled with current knowledge
before anything is written, and every write goes through this module.

1. Candidates — the existing hybrid search (search.search_lanes, knowledge lane, FTS + vectors) on the statement,
   plus this thread's current items; only current items (status derived/verified, valid_to unset or in the future)
   of the readable generations (+ the run's own staging generation in a pilot).
2. Verdict — new / confirms / enriches / corrects / replaces / contradicts / ignore, and the target item:
   deterministic when it can be (no candidate → new; same kind and same text → confirms), otherwise Walter Decision,
   need `memory.reconcile`, with the questions Memory declares (manifest/decisions.json `reconcile_target`,
   `reconcile`), batched: one decision for up to BATCH statements of a segment, memoised on its exact inputs
   (processing.decide_once: a replay never asks twice). Deterministic guards follow: an assistant's claim never
   corrects or replaces the owner's word (→ contradicts), an unsure replacement is kept as new with `maybe_updates`.
3. Lifecycle — a statement about the progress of a goal, decision or commitment (an action announced, under way,
   reported done, a result, a cancellation) advances that item instead of creating another one. "verified" needs a
   proof (proof()): tool results of the thread's session in the window, a passing check, the owner's confirmation;
   an agent's report alone stays "executed". Run Plane tasks of the thread close the goals they carried.
4. Write gate — apply(): atomic per segment, every change recorded in core.derived_changes (before/after, verdict,
   decider, proof, tag). Replaced or corrected knowledge is superseded (valid_to set, superseded_by), kept in its
   lineage and readable through history(); contradictions mark both items contested until settled; transient states
   carry valid_to. In a pilot (staging generation), changes to served items are recorded `staged` and never applied.
   revert(tag) undoes a tagged run exactly from these rows, evidence added to existing items included.
"""
from __future__ import annotations

import itertools
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import privacy
from .db import connection

log = logging.getLogger("walter.knowledge")

PROCESSOR = "l3.extract"
NEED = "memory.reconcile"
VERSION = "1"
VERDICTS = ("new", "confirms", "enriches", "corrects", "replaces", "contradicts", "ignore")
LIVE = ("derived", "verified")
FIELDS = ("status", "content", "attributes", "source_event_ids", "valid_to", "stage", "lineage_id", "confidence",
          "epistemic", "scope")
# lifecycle order of a goal / decision / commitment: a stage only moves forward; closing stages end it
ORDER = {"proposed": 0, "requested": 0, "stated": 0, "decided": 1, "accepted": 1, "open": 1, "in_progress": 2,
         "executed": 3, "verified": 4, "done": 5, "cancelled": 5, "abandoned": 5}
CLOSED = {"done", "cancelled", "abandoned"}
LIFECYCLE_KINDS = {"goal", "decision", "commitment"}
# an enriching statement takes the target's place only for the same intention or rule restated with more detail;
# about a fact it is a complement (linked, both current): facts on one subject that say different things are both
# true, and the pilot of 2026-11-19 showed decision models calling them « enriches » (half of 25 pairs wrong)
ENRICH_SUPERSEDES = {"goal", "decision", "commitment", "preference", "constraint"}
PROGRESS_ACTS = {"action", "result", "cancel"}
SEARCH = True     # the hybrid search finds candidates in other threads (tests turn it off unless they test it)
DEFAULTS = {"mode": "decision", "candidates": 5, "existing_candidates": 8, "batch": 12, "min_confidence": 0.5, "state_ttl_days": 7}


def settings() -> dict:
    from . import organic
    return {**DEFAULTS, **(organic.settings().get("reconcile") or {})}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def overlap(a: str, b: str) -> float:
    x, y = set(_norm(a).split()), set(_norm(b).split())
    return len(x & y) / len(x | y) if x and y else 0.0


def _j(v):
    """A JSON-comparable image of a column value (datetimes and uuids as text)."""
    return json.loads(json.dumps(v, default=str))


# ───────────────────────────── 1. candidates ─────────────────────────────
def _current(conn, ids: list[str], gens: list[str]) -> list[dict]:
    if not ids:
        return []
    return conn.execute("""select item_id::text, kind, content, stage, scope, epistemic, status, generation,
                                  lineage_id::text, privacy_class, attributes, coalesce(valid_from, created_at) as at
                           from core.derived_items where item_id = any(%s::uuid[]) and derived_by = %s
                             and status = any(%s) and (valid_to is null or valid_to > now()) and kind <> 'summary'
                             and generation = any(%s)
                           order by array_position(%s::uuid[], item_id)""",      # the ranking given (nearest first):
                        (ids, PROCESSOR, list(LIVE), gens, ids)).fetchall()      # the same inputs → the same decision


def candidates(conn, st: dict, pool: list[dict], gens: list[str], k: int) -> list[dict]:
    """Up to k current items that may be about the same thing as statement st: the hybrid search first, then this
    thread's items (pool) by word overlap. Cloud-readable only (they go to a decision model)."""
    found: list[str] = []
    try:
        if not SEARCH:
            raise LookupError("search off")
        from . import search
        rows = search.search_lanes(st["text"], lanes=("knowledge",), sources=[PROCESSOR], generations=gens,
                                   limit=k + 3).get("knowledge", [])
        found = [r["ref_id"] for r in rows if r.get("ref_id")]
    except Exception as e:  # noqa: BLE001 — the embedder is an optimisation; the thread's items still compete
        log.debug("candidate search failed: %s", e)
    # the same subject's items — its previous states by name, its nearest in meaning — take turns with the open
    # search's: none fills the k + 2 places alone; a statement already stored is never its own candidate
    named, near = same_subject(conn, st, gens, k)
    found = [x for row in itertools.zip_longest(named, found, near) for x in row if x and x != st.get("item_id")]
    by_id = {r["item_id"]: r for r in _current(conn, list(dict.fromkeys(found)), gens)}
    out = [by_id[i] for i in dict.fromkeys(found) if i in by_id]
    for r in sorted(pool, key=lambda r: -overlap(st["text"], r["content"])):
        if len(out) >= k + 2:
            break
        if r["item_id"] not in {o["item_id"] for o in out} and overlap(st["text"], r["content"]) >= 0.12:
            out.append(r)
    out = [r for r in out if privacy.cloud_readable(r["privacy_class"])]
    return out[:k + 2]


GENERIC_SUBJECTS = {"", "other", "owner", "monsieur"}


def subject_key(s: str | None) -> str:
    """« project:W.Alter », « project:walter », « project:Walter Memory » / « project:walter-memory »: one key each."""
    return re.sub(r"[^a-z0-9:]", "", (s or "").lower())


GENERIC_KEYS = {subject_key(x) for x in GENERIC_SUBJECTS}


def same_subject(conn, st: dict, gens: list[str], k: int) -> tuple[list[str], list[str]]:
    """The current items about the same subject (attributes.subject: project:x, person:y, a tool…) or the same
    project, nearest in meaning to the statement: the same property worded differently, which the open search over
    every piece of knowledge can rank too low (2026-11-19, owner: « retrouver les connaissances qui portent sur la même
    propriété d'une même entité ou d'un même projet, même si elles sont formulées différemment »). Local vectors only."""
    subj = (st.get("subject") or "").strip()
    proj = st.get("project")
    if subject_key(subj) in GENERIC_KEYS and not proj:
        return [], []
    try:
        from . import search
        qv = search.vec(search.embed([st["text"]])[0])
        rows = conn.execute("""
            with same as (select item_id from core.derived_items
                          where derived_by = %s and generation = any(%s) and status = any(%s) and kind <> 'summary'
                            and (valid_to is null or valid_to > now())
                            and ((%s::text <> '' and regexp_replace(lower(attributes->>'subject'), '[^a-z0-9:]', '', 'g')
                                                     = regexp_replace(lower(%s), '[^a-z0-9:]', '', 'g'))
                                 or (%s::text is not null and attributes->'projects' ? %s)))
            select c.ref_id::text id, min(c.embedding <=> %s::vector) d from search.chunks c join same on same.item_id = c.ref_id
            where c.kind = 'derived' and c.embedding is not null and not c.hidden group by 1 order by 2 limit %s""",
            (PROCESSOR, gens, list(LIVE), subj if subject_key(subj) not in GENERIC_KEYS else "",
             subj, proj, proj, qv, k)).fetchall()
        near = [r["id"] for r in rows if r["d"] <= SAME_SUBJECT_MAX_DISTANCE]
        # the thing whose state is told (a component, a tool, a model): its name, shared with the subject's other
        # items, and among them the latest said before this statement — its previous state, by fact time. Local
        # vectors miss « Hermes est entièrement retiré » ↔ « Hermes assure encore en production » (0.68, rank 41 of
        # the subject's 54 items naming Hermes, first production slice 19/11); each state meeting the one before it,
        # the chain links up item after item
        terms = anchors(st["text"], subj)
        named: list[str] = []
        if terms:
            rows = conn.execute("""
                select i.item_id::text id from core.derived_items i
                where i.derived_by = %s and i.generation = any(%s) and i.status = any(%s) and i.kind <> 'summary'
                  and (i.valid_to is null or i.valid_to > now())
                  and ((%s::text <> '' and regexp_replace(lower(i.attributes->>'subject'), '[^a-z0-9:]', '', 'g')
                                           = regexp_replace(lower(%s), '[^a-z0-9:]', '', 'g'))
                       or (%s::text is not null and i.attributes->'projects' ? %s))
                  and i.content ~* %s and (%s::timestamptz is null or coalesce(i.valid_from, i.created_at) <= %s::timestamptz)
                order by coalesce(i.valid_from, i.created_at) desc limit %s""",
                (PROCESSOR, gens, list(LIVE), subj if subject_key(subj) not in GENERIC_KEYS else "", subj, proj, proj,
                 rf"\m{re.escape(terms[0])}\M", st.get("at"), st.get("at"), k + 1)).fetchall()
            named = [r["id"] for r in rows]
        return named, near
    except Exception as e:  # noqa: BLE001 — an addition to the candidates; never blocks a reconciliation
        log.debug("same-subject candidates failed: %s", e)
        return [], []


SAME_SUBJECT_MAX_DISTANCE = 0.6     # cosine distance: beyond it, another property of the subject
NAME = re.compile(r"[A-Za-zÀ-ÿ][\w.\-]*[\w]")
NOT_NAMES = {"selon", "walter", "w.alter", "monsieur", "the", "le", "la", "les", "un", "une", "il", "elle", "si",
             "depuis", "après", "avant", "au", "en", "dans"}


def anchors(text: str, subject: str = "", n: int = 4) -> list[str]:
    """The names in a statement — a capitalised word past the first, or a token with a digit, a dot, a hyphen or an
    underscore (DSH, Hermes, walter-llm, d1.2-ultra) — minus the subject's own words and the usual openers."""
    own = set(re.split(r"[^a-z0-9]+", (subject or "").lower().split(":", 1)[-1])) - {""}
    out: list[str] = []
    for i, m in enumerate(NAME.finditer(text or "")):
        w = m.group(0).strip(".-")
        lw = w.lower()
        if len(w) < 3 or lw in NOT_NAMES or lw in own or any(p in own for p in re.split(r"[^a-z0-9]+", lw) if p):
            continue
        if (i > 0 and w[0].isupper()) or re.search(r"[0-9._\-]", w) or (len(w) > 1 and any(ch.isupper() for ch in w[1:])):
            if lw not in (x.lower() for x in out):
                out.append(w)
    return out[:n]


# ───────────────────────────── 2. verdicts ─────────────────────────────
def _declared() -> tuple[dict, dict, dict]:
    """The questions Memory declares for Walter Decision (manifest/decisions.json): the single source of their text."""
    p = Path(__file__).resolve().parent.parent / "manifest" / "decisions.json"
    sig = json.loads(p.read_text())["signals"]
    return sig["reconcile_target"]["question"], sig["reconcile"]["question"], sig["reconcile_work"]["question"]


def open_work(pool: list[dict], k: int = 6) -> list[dict]:
    """The goals, requests, decisions and commitments still open among an statement's surroundings (this thread's
    items, similar ones from other conversations, the segment's earlier statements), most recent last: what an action
    or a result may be carrying out."""
    out = [r for r in pool if r["kind"] in LIFECYCLE_KINDS and (r.get("stage") or "") not in CLOSED
           and privacy.cloud_readable(r["privacy_class"])]
    return out[-k:]


def deterministic(st: dict, cands: list[dict]) -> tuple[str, str | None, str] | None:
    """(verdict, target, rule) when no model is needed."""
    if not cands:
        return "new", None, "no_candidate"
    for c in cands:
        if c["kind"] == st["kind"] and (_norm(c["content"]) == _norm(st["text"]) or overlap(c["content"], st["text"]) >= 0.9):
            return "confirms", c["item_id"], "same_text"
    return None


def _answer_conf(a: dict) -> float | None:
    if not isinstance(a, dict):
        return None
    c = a.get("confidence")
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return float(c)
    p = a.get("probabilities")
    if isinstance(p, dict) and p:
        vals = [v for v in p.values() if isinstance(v, (int, float))]
        return float(max(vals)) if vals else None
    return None


WHO = {"stated_owner": "owner", "agent_reported": "assistant", "stated_third_party": "third party",
       "observed": "observed", "inferred": "assistant (hypothesis)"}


MAX_QUESTIONS = 32   # walter-llm /v1/decisions: at most 32 questions per decision


def question_count(st: dict) -> int:
    """Questions judge() asks for one statement: target + verdict, + work when it may be a step of open work."""
    return 2 + (1 if any(True for _ in st.get("open_work") or []) and st.get("act") in PROGRESS_ACTS else 0)


def batches(pending: list, size: int) -> list[list]:
    """Cut (sid, statement, candidates) into decisions of at most `size` statements and MAX_QUESTIONS questions
    (production 19/11: a dense segment of 12 statements with open work asked 36 and was refused)."""
    out, cur, n = [], [], 0
    for p in pending:
        q = question_count(p[1])
        if cur and (len(cur) >= max(1, size) or n + q > MAX_QUESTIONS):
            out.append(cur); cur, n = [], 0
        cur.append(p); n += q
    return out + ([cur] if cur else [])


def judge(batch: list[tuple[str, dict, list[dict]]], *, privacy_class: str, budget: str) -> dict:
    """One Walter Decision for a batch of (sid, statement, candidates) → {sid: (verdict, target item_id, confidence)}.
    Memoised on its exact inputs (processing.decide_once): a replay of the same statements never asks again."""
    from . import llm, processing
    tq, vq, wq = _declared()
    items, refs, questions, statements = {}, [], {}, {}

    def ref(c: dict) -> str:
        key = next((k for k, v in items.items() if v["id"] == c["item_id"]), None)
        if not key:
            key = f"K{len(items) + 1}"
            items[key] = {"id": c["item_id"], "type": c["kind"], "stage": c.get("stage") or "stated",
                          "said_by": WHO.get(c.get("epistemic") or "", "?"), "at": str(c.get("at") or "")[:16],
                          "text": c["content"][:600]}
            if not c["item_id"].startswith("seg:"):
                refs.append(c["item_id"])
        return key
    for sid, st, cands in batch:
        crit = {ref(c): c["content"][:160] for c in cands}
        crit["none"] = "none of these items is about the same thing"
        work = [g for g in st.get("open_work") or [] if st["act"] in PROGRESS_ACTS]
        if work:      # lifecycle: is this action / result the work of an open goal, request or decision?
            questions[f"{sid}_work"] = {"type": "choice",
                                        "criteria": {**{ref(g): g["content"][:160] for g in work},
                                                     "none": "none: it is not work on any of these"},
                                        "instructions": f"{wq['instructions']} Statement {sid}."}
        statements[sid] = {"type": st["act"], "stage": st["stage"], "said_by": WHO.get(st["epistemic_v"], "?"),
                           "at": str(st["at"])[:16], "text": st["text"][:600]}
        questions[f"{sid}_target"] = {"type": "choice", "criteria": crit,
                                      "instructions": f"{tq['instructions']} Statement {sid}."}
        questions[f"{sid}_verdict"] = {"type": "choice", "criteria": vq["criteria"],
                                       "instructions": f"{vq['instructions']} Statement {sid}, against the target "
                                                       f"you chose for {sid}_target."}
    state = {"statements": statements, "items": {k: {kk: vv for kk, vv in v.items() if kk != "id"}
                                                 for k, v in items.items()}}

    def call():
        a = llm.decide(state, questions, processor=NEED, privacy_class=privacy_class, budget=budget,
                       purpose=f"reconcile {len(batch)} statements", timeout=60)
        ans = a.get("answers") or {}
        return {sid: {"target": (ans.get(f"{sid}_target") or {}).get("choice"),
                      "verdict": (ans.get(f"{sid}_verdict") or {}).get("choice"),
                      "confidence": _answer_conf(ans.get(f"{sid}_verdict")),
                      "work": (ans.get(f"{sid}_work") or {}).get("choice"),
                      "work_confidence": _answer_conf(ans.get(f"{sid}_work"))} for sid, _, _ in batch}, a.get("model")

    outcome, _ = processing.decide_once(NEED, VERSION, {"state": state, "questions": questions}, call,
                                        privacy_class=privacy_class, refs=refs)
    res = {}
    for sid, _, _ in batch:
        o = outcome.get(sid) or {}
        w = o.get("work")
        if w in items and f"{sid}_work" in questions and w in questions[f"{sid}_work"]["criteria"]:
            res[sid] = ("enriches", items[w]["id"], o.get("work_confidence"))   # a step of that goal: it advances
            continue
        t = o.get("target")
        res[sid] = (o.get("verdict") if o.get("verdict") in VERDICTS else "new",
                    items[t]["id"] if t in items else None, o.get("confidence"))
    return res


def confirmed(target: dict) -> bool:
    """Knowledge that is more than a declaration: the owner's word, confirmed by him, or a result proven by a check."""
    a = target.get("attributes") or {}
    return (target.get("epistemic") == "stated_owner" or target.get("status") == "verified"
            or bool(a.get("confirmed_by_owner")) or (a.get("proof") or {}).get("level") in ("checked", "confirmed"))


CHANGE_MARK = re.compile(r"(?i)(\bde nouveau\b|\bà nouveau\b|\bdésormais\b|\bdorénavant\b|\bn['’]est plus\b|"
                         r"\bne \w+ plus\b|\bn['’]\w+ plus\b|\bplus aucun|réactiv|remplacé|\bretiré|désinstall|"
                         r"\bno longer\b|\bagain\b|\breplaced\b|\bretired\b|\breactivated\b)")


def later_in_fact(st: dict, target: dict) -> bool:
    a, b = st.get("at"), target.get("at")
    try:
        return bool(a and b and a > b)
    except TypeError:
        return str(a) > str(b)


def guard(st: dict, verdict: str, target: dict | None, conf: float | None, min_conf: float) -> tuple[str, str | None]:
    """Deterministic rules over the model's verdict → (verdict, note)."""
    if verdict in ("new", "ignore"):
        return verdict, None
    if target is None:
        return "new", "no_target"
    # a contact's word replaces only what the same person said before, never another person's (E2E 20/11)
    if verdict in ("corrects", "replaces") and st.get("by_contact") and not st["by_owner"] \
            and (target.get("attributes") or {}).get("speaker_id") not in (st.get("speaker_ids") or []):
        return "contradicts", "other_speaker"
    if verdict in ("corrects", "replaces") and not st["by_owner"] and target.get("epistemic") == "stated_owner" \
            and not is_progress(st, target, verdict):
        return "contradicts", "agent_vs_owner"      # an assistant's claim never overrides the owner's word
    # production 19/11 (owner: « une déclaration non vérifiée ne doit pas écraser un fait confirmé »): a declaration
    # that is not the owner's never replaces confirmed or proven knowledge; it is contested (or a linked complement)
    if not st["by_owner"] and confirmed(target) and not is_progress(st, target, verdict):
        if verdict in ("corrects", "replaces"):
            return "contradicts", "unverified_vs_confirmed"
        if verdict == "enriches":
            return "enriches", "complement_only"
    if verdict in ("corrects", "replaces") and target["kind"] in ("constraint", "preference", "correction") \
            and not st["by_owner"]:
        return "contradicts", "owner_rule"
    # 2026-11-19 (owner: « en cas d'incertitude, conserver une contradiction explicite plutôt que de remplacer
    # arbitrairement une connaissance »): an unsure replacement keeps both, contested; an unsure contradiction is not
    # one (likely another claim)
    if verdict in ("corrects", "replaces") and conf is not None and conf < min_conf:
        # the statement itself says the state changed (« de nouveau active », « n'est plus », « retiré ») and was
        # said after the target, in fact time: the evidence and the dates settle what the model's confidence does not
        if verdict == "replaces" and CHANGE_MARK.search(st["text"] or "") and later_in_fact(st, target):
            return verdict, "explicit_change"
        return "contradicts", "unsure"
    if verdict == "contradicts" and conf is not None and conf < min_conf:
        return "new", "unsure"
    # an unsure "same intention, more precise" would retire its target: kept as a linked complement, both current
    # (first production slice 19/11: an evolution judged at 0.21 had superseded its target)
    if verdict == "enriches" and conf is not None and conf < min_conf:
        return "enriches", "complement_only"
    return verdict, None


# ───────────────────────────── 3. proof ladder ─────────────────────────────
# a check = a command that tests something, run by a tool that executes commands (not a report, a status update, a
# help page or a search: the pilot of 2026-11-19 showed them taken for checks)
CHECK = re.compile(r"(?i)(pytest|unittest|\bnpm (run )?test|\bgo test\b|cargo test|walter check|\bhealth\b|"
                   r"systemctl (is-active|status)|\bcurl\s|--dry-run|\bsmoke\b|\bassert\b|\bdiff\b)")
EXEC_TOOLS = re.compile(r"(?i)^(bash|exec|exec_command|shell|local_shell|run_command|terminal|powershell)$")
# a statement saying the work could not be checked is never a verified result, whatever ran around it
UNVERIFIED = re.compile(r"(?i)(pas (avoir )?(pu|encore|été) (être )?(vérifi|test|contrôl)|non (vérifi|test)|sans (l.)?avoir (vérifi|test)|"
                        r"impossible de (vérifier|tester)|reste à (vérifier|tester)|à vérifier|échou|en échec|"
                        r"not (been )?(verified|tested)|could not (verify|test)|unverified|untested)")
FAILED = re.compile(r"(?i)(exit(ed)?( with)? code:? ?[1-9]|process exited with code [1-9]|traceback \(most recent|"
                    r"\b\d+ failed\b|\bFAILED\b|error:|errors? occurred|command not found|no such file)")
PASSED = re.compile(r"(?i)(\b\d+ passed\b|\bok\b|\bsuccess|\bactive\b|\b200\b|réussi)")


def proof(conn, source: str, thread_id: str, until_at, *, owner: bool = False) -> dict:
    """What backs a report of work in this thread, read from walter_logs (what the agent actually did) between the
    owner's last message before the report and the report itself. Levels: claimed (no tool result) · executed (tool
    results, none failing at the end) · checked (a check — tests, health, curl… — that passed, and no later failing
    check) · refuted (the last check failed) · confirmed (the owner says so). The scope is that window of that session, nothing more."""
    if owner:
        return {"level": "confirmed", "by": "owner"}
    since = conn.execute("""select max(occurred_at) as t from core.events where source = %s and thread_id = %s
                            and event_type = 'message.sent' and occurred_at < %s""",
                         (source, thread_id, until_at)).fetchone()["t"] or (until_at - timedelta(hours=2))
    sessions = [r["session_id"] for r in conn.execute(
        """select session_id from walter_logs.sessions where session_id = %s or session_id like %s""",
        (thread_id, f"%/{thread_id}"))]
    if not sessions:
        return {"level": "claimed", "sessions": 0}
    rows = conn.execute("""select r.status, left(r.text, 4000) as out, left(c.text, 2000) as cmd, coalesce(c.tool, r.tool) as tool
                           from walter_logs.events r left join walter_logs.events c
                             on c.session_id = r.session_id and c.call_id = r.call_id and c.type = 'tool/call'
                           where r.session_id = any(%s) and r.type = 'tool/result'
                             and r.occurred_at > %s and r.occurred_at <= %s + interval '1 minute'
                           order by r.occurred_at, r.seq""", (sessions, since, until_at)).fetchall()
    ok = err = 0
    checks, last = [], None
    for r in rows:
        bad = r["status"] == "error" or bool(FAILED.search(r["out"] or ""))
        err += bad
        ok += not bad
        if EXEC_TOOLS.match(r["tool"] or "") and CHECK.search(r["cmd"] or ""):
            checks.append(not bad)
            seen = (FAILED if bad else PASSED).search(r["out"] or "")
            last = {"tool": r["tool"], "cmd": " ".join((r["cmd"] or "").split())[:160],
                    "out": (r["out"] or "")[max(0, seen.start() - 60):seen.end() + 60].replace("\n", " ") if seen else ""}
    level = "claimed"
    if ok:
        level = "executed"
    if checks and checks[-1]:
        level = "checked"
    elif checks:
        level = "refuted"                  # the last check failed: the report is contradicted by what ran
    return {"level": level, "tools_ok": ok, "tools_error": err, "checks": len(checks), "checks_ok": sum(checks),
            "since": str(since), "until": str(until_at), "sessions": len(sessions),
            **({"last_check": last} if last else {})}       # what the proof rests on, readable by Monsieur


def verifies(st: dict, pr: dict | None) -> bool:
    """A result is verified by a passing check of that work or the owner's word — never when it says it was not."""
    return bool(pr) and pr.get("level") in ("checked", "confirmed") and not UNVERIFIED.search(st.get("text") or "")


def is_progress(st: dict, target: dict, verdict: str) -> bool:
    """Does this statement move its target along its lifecycle (rather than restate or replace it)? An action, a
    result or a cancellation about a goal / decision / commitment; a decision that takes up a goal or a proposal."""
    if target["kind"] not in LIFECYCLE_KINDS or verdict not in ("confirms", "enriches", "replaces", "corrects"):
        return False
    if st["act"] in ("action", "result", "cancel"):
        return True
    return st["act"] == "decision" and verdict in ("confirms", "enriches") and (
        target["kind"] in ("goal", "commitment") or (target.get("stage") or "") == "proposed")


def progress_stage(st: dict, target: dict, pr: dict | None) -> str | None:
    """The stage a progress statement brings its target to, or None (forward only; closing is final)."""
    cur = target.get("stage") or "stated"
    if cur in CLOSED:
        return None
    act, s = st["act"], st["stage"]
    new = None
    if act == "cancel" or s in ("abandoned", "cancelled"):
        new = "abandoned" if st["by_owner"] else None        # only the owner gives up on his goal
    elif act == "decision" and s == "decided":
        new = "accepted" if target["kind"] in ("goal", "commitment") else "decided"
    elif act == "action":
        new = {"open": "accepted", "accepted": "accepted", "in_progress": "in_progress", "executed": "executed"}.get(s)
    elif act == "result":
        new = "verified" if verifies(st, pr) else "executed"
    if not new or ORDER.get(new, 0) <= ORDER.get(cur, 0):
        return None
    return new


# ───────────────────────────── 4. the write gate ─────────────────────────────
class Gate:
    """All writes of one segment, in one transaction (the caller's connection). generation = where new items go;
    staged = a pilot: served items (another generation) are never changed, their changes are recorded only."""

    def __init__(self, conn, *, generation: str, tag: str | None, segment: str | None, where: str | None = None):
        self.conn, self.generation, self.tag, self.segment = conn, generation, tag, segment
        self.where = where                  # "source/thread" of the statements: an item stated in several threads
                                            # lists them (attributes.threads), so each thread's readers see it
        self.pilot = generation != "g1"
        self.changed: list[str] = []        # items whose readable state changed (views, index)
        self.staged: list[dict] = []

    def _row(self, item_id: str) -> dict:
        return self.conn.execute(f"""select item_id::text, generation, kind, {', '.join(FIELDS)}
                                     from core.derived_items where item_id = %s for update""", (item_id,)).fetchone()

    def _record(self, *, key, item_id, op, verdict=None, decided_by=None, confidence=None, before=None, after=None,
                provenance=None, proof=None, reason=None, staged=False, lineage=None) -> bool:
        r = self.conn.execute("""insert into core.derived_changes (key, item_id, lineage_id, op, verdict, decided_by,
                                     confidence, tag, segment_id, generation, staged, before, after, provenance, proof, reason)
                                 values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                 on conflict (key) do nothing returning change_id""",
                              (key, item_id, lineage, op, verdict, decided_by, confidence, self.tag, self.segment,
                               self.generation, staged, json.dumps(_j(before)) if before is not None else None,
                               json.dumps(_j(after)) if after is not None else None,
                               json.dumps(provenance or []), json.dumps(_j(proof)) if proof else None, reason)).fetchone()
        return bool(r)

    def _prov(self, target: str, stype: str, sid: str, role: str) -> dict | None:
        r = self.conn.execute("""insert into core.provenance (target_table, target_id, source_type, source_id, role)
                                 values ('derived_items', %s, %s, %s, %s) on conflict do nothing returning 1""",
                              (target, stype, sid, role)).fetchone()
        return {"target": target, "source_type": stype, "source": sid, "role": role} if r else None

    def change(self, item_id: str, fields: dict, *, op: str, key: str, verdict=None, decided_by=None,
               confidence=None, evidence: list[str] | None = None, links: list[tuple[str, str, str]] | None = None,
               proof=None, reason=None) -> str:
        """Change an existing item: 'applied', 'staged' (pilot, served item) or 'duplicate' (already done)."""
        row = self._row(item_id)
        if row is None:
            return "missing"
        if links:   # never a link across generations (core.guard_generation_provenance): a pilot item linked to a
            ends = [x for t_, s_, _ in links for x in (t_, s_)]   # served one is recorded with the change, not applied
            gen = {r["item_id"]: r["generation"] for r in self.conn.execute(
                "select item_id::text, generation from core.derived_items where item_id = any(%s::uuid[])", (ends,))}
            cross = [list(l) for l in links if gen.get(l[0]) != gen.get(l[1])]
            if cross:
                links = [l for l in links if list(l) not in cross]
                fields = {**fields}
                extra = {"+links_not_applied": cross}
            else:
                extra = {}
        else:
            extra = {}
        if self.pilot and row["generation"] != self.generation:
            ok = self._record(key=key, item_id=item_id, op=op, verdict=verdict, decided_by=decided_by,
                              confidence=confidence,
                              after=fields | ({"+evidence": evidence} if evidence else {}) | extra,
                              proof=proof, reason=reason, staged=True, lineage=row["lineage_id"])
            if ok:
                self.staged.append({"op": op, "item": item_id, "verdict": verdict, "segment": self.segment})
            return "staged" if ok else "duplicate"
        if evidence:
            fields = {**fields, "source_event_ids": sorted({*map(str, row["source_event_ids"] or []), *evidence})}
        before = {k: row[k] for k in fields}
        if not self._record(key=key, item_id=item_id, op=op, verdict=verdict, decided_by=decided_by,
                            confidence=confidence, before=before, after=fields | extra, proof=proof, reason=reason,
                            lineage=row["lineage_id"]):
            return "duplicate"
        sets, args = [], []
        for k, v in fields.items():
            if k == "attributes":
                sets.append("attributes = %s::jsonb"); args.append(json.dumps(_j(v), ensure_ascii=False))
            elif k == "source_event_ids":
                sets.append("source_event_ids = %s::uuid[]"); args.append(list(v))
            elif k == "lineage_id":
                sets.append("lineage_id = %s::uuid"); args.append(v)
            else:
                sets.append(f"{k} = %s"); args.append(v)
        self.conn.execute(f"update core.derived_items set {', '.join(sets)} where item_id = %s", (*args, item_id))
        prov = [p for e in evidence or [] if (p := self._prov(item_id, "event", e, "supports"))]
        prov += [p for tgt, src, role in links or [] if (p := self._prov(tgt, "derived", src, role))]
        if prov:
            self.conn.execute("update core.derived_changes set provenance = %s where key = %s", (json.dumps(prov), key))
        self.changed.append(item_id)
        return "applied"

    def create(self, row: dict, *, key: str, verdict: str, decided_by: str, confidence=None, lineage: str | None = None,
               reason=None) -> str | None:
        """Insert a new item (row = core.derived_items columns) → its id, or None if this statement was written already."""
        cols = list(row)
        vals = [json.dumps(row[c], ensure_ascii=False, default=str) if c in ("attributes", "source_refs") else row[c]
                for c in cols]
        casts = {"source_event_ids": "%s::uuid[]", "attributes": "%s::jsonb", "source_refs": "%s::jsonb"}
        r = self.conn.execute(f"""insert into core.derived_items ({', '.join(cols)}) values
                                  ({', '.join(casts.get(c, '%s') for c in cols)})
                                  on conflict (derived_by, (source_refs->>'ref')) where source_refs ? 'ref' do nothing
                                  returning item_id::text""", vals).fetchone()
        if not r:
            return None
        new_id = r["item_id"]
        lin = lineage or new_id
        self.conn.execute("update core.derived_items set lineage_id = %s::uuid where item_id = %s", (lin, new_id))
        self._record(key=key, item_id=new_id, op="create", verdict=verdict, decided_by=decided_by,
                     confidence=confidence, after={"status": "derived"}, reason=reason, lineage=lin)
        self.changed.append(new_id)
        return new_id


def apply(gate: Gate, st: dict, verdict: str, target: dict | None, *, row: dict, key: str, decided_by: str,
          confidence=None, note: str | None = None, proof_of=None) -> dict:
    """One reconciled statement through the gate → {"op", "item", ...}. row = the new item's columns if one is made."""
    ev = row["source_event_ids"]
    at = row["valid_from"]
    meta = {"verdict": verdict, "decided_by": decided_by, "confidence": confidence}
    attrs = row["attributes"]
    attrs["reconcile"] = {"verdict": verdict, "by": decided_by, **({"confidence": round(confidence, 3)} if confidence
                                                                     is not None else {}),
                          **({"target": target["item_id"]} if target else {}), **({"note": note} if note else {})}
    if verdict == "ignore":
        return {"op": "ignored"}
    if verdict == "new" or target is None:
        if note == "unsure" and target:
            attrs["maybe_updates"] = target["item_id"]
        new = gate.create(row, key=f"{key}:create", **meta, reason=note)
        return {"op": "created" if new else "duplicate", "item": new}
    tid = target["item_id"]
    # lifecycle: a progress statement about a goal / decision / commitment advances it, no second item
    if is_progress(st, target, verdict):
        pr = proof_of(st) if st["act"] == "result" or st["stage"] == "executed" else None
        new_stage = progress_stage(st, target, pr)
        cur = gate._row(tid)
        a = dict(cur["attributes"] or {})
        steps = list(a.get("progress") or [])
        steps.append({"at": str(at), "act": st["act"], "stage": st["stage"], "text": st["text"][:300],
                      "said_by": st["epistemic_v"], **({"proof": pr["level"]} if pr else {})})
        a["progress"] = steps[-12:]
        if gate.where:
            a["threads"] = sorted({*(a.get("threads") or []), gate.where})
        if pr:
            a["proof"] = pr
        fields = {"attributes": a}
        if st["act"] == "decision" and st["by_owner"] and cur["epistemic"] != "stated_owner":
            fields["epistemic"] = "stated_owner"      # the owner took the proposal: it is his decision now
        if new_stage:
            fields["stage"] = new_stage
            if new_stage == "verified":
                fields["status"] = "verified"
        res = gate.change(tid, fields, op="advance", key=f"{key}:advance:{tid}", evidence=ev, proof=pr,
                          reason=f"{cur['stage']}→{new_stage}" if new_stage else "progress", **meta)
        return {"op": "advanced" if new_stage else "progress", "item": tid, "stage": new_stage, "result": res,
                "proof": (pr or {}).get("level")}
    if verdict == "confirms":
        cur = gate._row(tid)
        a = dict(cur["attributes"] or {})
        a["confirmations"] = int(a.get("confirmations") or 0) + 1
        if gate.where:
            a["threads"] = sorted({*(a.get("threads") or []), gate.where})
        if st["by_owner"] and cur["epistemic"] != "stated_owner":
            a["confirmed_by_owner"] = True
        settled = []
        if st["by_owner"] and a.get("contested"):      # the owner takes one side of a contradiction: it is settled
            a.pop("contested")
            settled = settle(gate, tid, at, key=key, meta=meta)
        res = gate.change(tid, {"attributes": a}, op="evidence", key=f"{key}:evidence:{tid}", evidence=ev, **meta)
        return {"op": "confirmed", "item": tid, "result": res, **({"settled": settled} if settled else {})}
    if verdict == "contradicts":
        if target.get("at") and target["at"] > at:    # an older statement replayed now: the target's past, no doubt on it
            new = gate.create(row, key=f"{key}:create", **meta, reason="replayed_older")
            if not new:
                return {"op": "duplicate"}
            res = gate.change(new, {"status": "superseded", "valid_to": target["at"],
                                    "attributes": {**attrs, "superseded_by": tid, "replayed_older": True}},
                              op="supersede", key=f"{key}:older:{new}", reason="replayed_older", **meta)
            return {"op": "older", "item": new, "target": tid, "result": res}
        new = gate.create({**row, "attributes": {**attrs, "contested": True}}, key=f"{key}:create", **meta,
                          reason=note)
        if not new:
            return {"op": "duplicate"}
        cur = gate._row(tid)
        res = gate.change(tid, {"attributes": {**(cur["attributes"] or {}), "contested": True}}, op="contest",
                          key=f"{key}:contest:{tid}", links=[(new, tid, "contradicts")], **meta, reason=note)
        return {"op": "contested", "item": new, "target": tid, "result": res}
    if verdict == "enriches" and (note == "complement_only"
                                  or not (st["kind"] == target["kind"] and target["kind"] in ENRICH_SUPERSEDES)):
        attrs["enriches"] = tid                    # a complement: a new item linked to the target, both current
        new = gate.create({**row, "attributes": attrs}, key=f"{key}:create", **meta, reason=note)
        if not new:
            return {"op": "duplicate"}
        res = gate.change(new, {"attributes": attrs}, op="link", key=f"{key}:link:{tid}",
                          links=[(new, tid, "enriches")], **meta, reason="complement")
        return {"op": "complemented", "item": new, "target": tid, "result": res}
    # enriches (same intention) / corrects / replaces: a new version in the target's lineage; the old one is no
    # longer current
    cur = gate._row(tid)
    same_gen = cur["generation"] == gate.generation
    if target["kind"] in LIFECYCLE_KINDS and st["kind"] == target["kind"]:     # a goal restated keeps its progress
        if ORDER.get(cur["stage"] or "", 0) > ORDER.get(row["stage"] or "", 0) and cur["stage"] not in CLOSED:
            row = {**row, "stage": cur["stage"]}
        if (cur["attributes"] or {}).get("progress"):
            attrs["progress"] = cur["attributes"]["progress"]
    attrs["version"] = int((cur["attributes"] or {}).get("version") or 1) + 1
    attrs["supersedes"] = tid
    new = gate.create({**row, "attributes": attrs}, key=f"{key}:create", **meta,
                      lineage=cur["lineage_id"] if same_gen else None, reason=note)
    if not new:
        return {"op": "duplicate"}
    stated_at = at
    if target.get("at") and target["at"] > stated_at:         # an older statement replayed now: the past of the target
        res = gate.change(new, {"status": "superseded", "valid_to": target["at"],
                                "attributes": {**attrs, "superseded_by": tid, "replayed_older": True}},
                          op="supersede", key=f"{key}:older:{new}", reason="replayed_older", **meta)
        return {"op": "older", "item": new, "target": tid, "result": res}
    res = gate.change(tid, {"status": "superseded", "valid_to": stated_at,
                            "attributes": {**(cur["attributes"] or {}), "superseded_by": new, "superseded_how": verdict}},
                      op="supersede", key=f"{key}:supersede:{tid}", links=[(new, tid, "supersedes")], **meta,
                      reason=note)
    return {"op": {"enriches": "enriched", "corrects": "corrected", "replaces": "replaced"}[verdict], "item": new,
            "target": tid, "result": res}


def settle(gate: Gate, winner: str, at, *, key: str, meta: dict) -> list[str]:
    """The owner confirmed one side of a contradiction: the items it was contradicting (or contradicted by) are no
    longer current — superseded by the winner, still in the history."""
    out = []
    for r in gate.conn.execute("""select case when target_id = %s then source_id else target_id end as other
                                  from core.provenance where target_table = 'derived_items' and role = 'contradicts'
                                    and source_type = 'derived' and %s in (target_id, source_id)""",
                               (winner, winner)).fetchall():
        other = gate._row(r["other"])
        if not other or other["status"] not in LIVE:
            continue
        a = {k: v for k, v in (other["attributes"] or {}).items() if k != "contested"}
        res = gate.change(r["other"], {"status": "superseded", "valid_to": at,
                                       "attributes": {**a, "superseded_by": winner, "superseded_how": "settled"}},
                          op="supersede", key=f"{key}:settle:{r['other']}", links=[(winner, r["other"], "supersedes")],
                          reason="settled_by_owner", **meta)
        if res in ("applied", "staged"):
            out.append(r["other"])
    return out


# ───────────────────────────── existing knowledge ─────────────────────────────
# 2026-11-19 (owner: « traiter … la coexistence de connaissances anciennes et nouvelles qui décrivent des états
# incompatibles … en réutilisant les mécanismes existants »): knowledge written before the reconciliation existed (the
# g1 extraction of 10–14/11) or judged "new" against fewer candidates goes once through the same candidates, the same
# batched decision (memory.reconcile, memoised), the same guards and the same gate, from its own point of view: is it
# the same claim as an item OLDER IN FACT (valid_from, the moment it was said — never the moment it was ingested), and
# then a complement, an evolution, a correction or a real contradiction? The older item is never removed: superseded
# with valid_to, contested, or linked — readable through history(). Driven by the catch-up loop (extract2.catchup),
# not per message; newest first, so each pair is judged once, from the later statement.
RELATE_KINDS = ("fact", "decision", "goal", "constraint", "preference", "commitment", "correction")


def _pending_existing(conn, limit: int, only: list[str] | None = None) -> list[dict]:
    r = conn.execute("select value from extraction.state where key = 'reconcile_existing_until'").fetchone()
    if r is None:       # the knowledge written before this pass: a finite backlog; later items are reconciled live
        until = datetime.now(timezone.utc)
        conn.execute("""insert into extraction.state (key, value) values ('reconcile_existing_until', %s)
                        on conflict (key) do nothing""", (json.dumps({"at": until.isoformat()}),))
    else:
        until = datetime.fromisoformat(r["value"]["at"])
    return conn.execute("""select item_id::text, kind, content, stage, scope, epistemic, status, generation,
                                  lineage_id::text, privacy_class, attributes, valid_from as at
                           from core.derived_items
                           where derived_by = %s and generation = 'g1' and status = any(%s) and kind = any(%s)
                             and (valid_to is null or valid_to > now()) and created_at < %s
                             and not attributes ? 'rereconciled'
                             and coalesce(attributes->'reconcile'->>'verdict', 'new') = 'new'
                             and (%s::uuid[] is null or item_id = any(%s::uuid[]))
                           order by valid_from desc, item_id limit %s""",
                        (PROCESSOR, list(LIVE), list(RELATE_KINDS), until, only, only, limit)).fetchall()


def _as_statement(r: dict) -> dict:
    a = r["attributes"] or {}
    return {"text": r["content"], "kind": r["kind"], "act": a.get("act") or r["kind"],
            "stage": r["stage"] or a.get("state") or "stated", "by_owner": r["epistemic"] == "stated_owner",
            "epistemic_v": r["epistemic"] or "?", "at": r["at"], "subject": a.get("subject"),
            "project": a.get("project") or ((a.get("projects") or [None])[0]), "open_work": [],
            "item_id": r["item_id"]}


def _linked(conn, a: str, b: str) -> bool:
    return bool(conn.execute("""select 1 from core.provenance where target_table = 'derived_items' and source_type = 'derived'
                                and ((target_id = %s and source_id = %s) or (target_id = %s and source_id = %s)) limit 1""",
                             (a, b, b, a)).fetchone())


def relate(gate: "Gate", s: dict, st: dict, verdict: str, t: dict | None, *, key: str, meta: dict,
           note: str | None) -> dict:
    """Two existing current items, s (later in fact) and its target t (earlier or same time), through the gate."""
    mark = {"at": datetime.now(timezone.utc).isoformat(), "verdict": verdict, "by": meta["decided_by"],
            **({"target": t["item_id"]} if t else {}), **({"note": note} if note else {})}
    sid = s["item_id"]

    def marked(extra: dict | None = None, row: dict | None = None) -> dict:
        cur = row or gate._row(sid)
        return {**(cur["attributes"] or {}), "rereconciled": mark, **(extra or {})}
    if verdict in ("new", "ignore") or t is None:
        gate.change(sid, {"attributes": marked()}, op="reconcile", key=f"{key}:mark", reason=note or verdict, **meta)
        return {"op": "kept"}
    tid = t["item_id"]
    tcur = gate._row(tid)
    if is_progress(st, t, verdict):      # work on that goal / decision: a step of it, both stay (the stage itself
        a = dict(tcur["attributes"] or {})   # moves only with a proof, in the live path)
        a["progress"] = (list(a.get("progress") or []) + [{"at": str(st["at"]), "act": st["act"], "stage": st["stage"],
                                                             "text": st["text"][:300], "said_by": st["epistemic_v"]}])[-12:]
        gate.change(tid, {"attributes": a}, op="advance", key=f"{key}:advance:{tid}", reason="progress", **meta)
        gate.change(sid, {"attributes": marked({"enriches": tid})}, op="link", key=f"{key}:link",
                    links=[(sid, tid, "enriches")], reason="progress", **meta)
        return {"op": "progress", "item": sid, "target": tid}
    if verdict == "confirms":            # the same claim twice: the stronger (proven / the owner's) or else the
        keep, drop = (s, t) if confirmed(s) and not confirmed(t) else (t, s)     # earlier one stays current
        kcur, dcur = gate._row(keep["item_id"]), gate._row(drop["item_id"])
        ka = {**(kcur["attributes"] or {}), "confirmations": int((kcur["attributes"] or {}).get("confirmations") or 0) + 1}
        if drop["epistemic"] == "stated_owner" and keep["epistemic"] != "stated_owner":
            ka["confirmed_by_owner"] = True
        if keep["item_id"] == sid:
            ka["rereconciled"] = mark
        gate.change(keep["item_id"], {"attributes": ka}, op="evidence", key=f"{key}:evidence",
                    evidence=[str(e) for e in dcur["source_event_ids"] or []], **meta)
        da = {**(dcur["attributes"] or {}), "superseded_by": keep["item_id"], "superseded_how": "duplicate"}
        if drop["item_id"] == sid:
            da["rereconciled"] = mark
        gate.change(drop["item_id"], {"status": "superseded", "attributes": da}, op="supersede",
                    key=f"{key}:duplicate", links=[(keep["item_id"], drop["item_id"], "supersedes")],
                    reason="duplicate", **meta)
        return {"op": "merged", "item": keep["item_id"], "target": drop["item_id"]}
    if verdict == "contradicts":
        gate.change(tid, {"attributes": {**(tcur["attributes"] or {}), "contested": True}}, op="contest",
                    key=f"{key}:contest:{tid}", reason=note, **meta)
        gate.change(sid, {"attributes": marked({"contested": True})}, op="contest", key=f"{key}:contest:{sid}",
                    links=[(sid, tid, "contradicts")], reason=note, **meta)
        return {"op": "contested", "item": sid, "target": tid}
    if verdict == "enriches" and (note == "complement_only"
                                  or not (st["kind"] == t["kind"] and t["kind"] in ENRICH_SUPERSEDES)):
        gate.change(sid, {"attributes": marked({"enriches": tid})}, op="link", key=f"{key}:link",
                    links=[(sid, tid, "enriches")], reason="complement", **meta)
        return {"op": "complemented", "item": sid, "target": tid}
    # enriches (same intention) / corrects / replaces: t no longer holds from the moment s was said; s joins t's
    # lineage as its next version
    ver = int((tcur["attributes"] or {}).get("version") or 1) + 1
    fields = {"attributes": marked({"supersedes": tid, "version": ver})}
    if str(gate._row(sid)["lineage_id"] or sid) == sid:      # no earlier versions of its own: it joins t's lineage
        fields["lineage_id"] = str(tcur["lineage_id"] or tid)
    gate.change(sid, fields, op="reconcile", key=f"{key}:version", reason=verdict, **meta)
    gate.change(tid, {"status": "superseded", "valid_to": st["at"],
                      "attributes": {**(tcur["attributes"] or {}), "superseded_by": sid, "superseded_how": verdict}},
                op="supersede", key=f"{key}:supersede:{tid}", links=[(sid, tid, "supersedes")], reason=note, **meta)
    return {"op": {"enriches": "enriched", "corrects": "corrected", "replaces": "replaced"}[verdict], "item": sid,
            "target": tid}


def reconcile_existing(limit: int = 120, *, tag: str | None = None, budget: str = "backfill",
                       only: list[str] | None = None) -> dict:
    """One slice of the existing-knowledge pass (see above) → counts. Idempotent (attributes.rereconciled, decisions
    memoised, change keys); reversible: knowledge.revert(tag), tag reconciliation-YYYY-MM-DD by default."""
    from . import search
    rc = settings()
    tag = tag or f"reconciliation-{datetime.now(timezone.utc):%Y-%m-%d}"
    out = {"tag": tag, "items": 0, "decisions": 0, "skipped": 0, "ops": {}}
    with connection() as conn:
        rows = _pending_existing(conn, limit, only)
        work = []
        for r in rows:
            st = _as_statement(r)
            cands = [] if not privacy.cloud_readable(r["privacy_class"]) else [
                c for c in candidates(conn, st, [], ["g1"], int(rc.get("existing_candidates") or rc["candidates"]))
                if c["item_id"] != r["item_id"] and c["lineage_id"] != r["lineage_id"] and c["at"] <= r["at"]
                and not _linked(conn, r["item_id"], c["item_id"])]
            work.append((r, st, cands))
    verdicts, pending = {}, []
    for i, (r, st, cands) in enumerate(work):
        det = deterministic(st, cands)
        if det:
            verdicts[i] = (det[0], det[1], None, f"deterministic:{det[2]}")
        else:
            pending.append((f"s{i + 1}", st, cands))
    for part in batches(pending, int(rc["batch"])):
        cls = privacy.strictest(*(c["privacy_class"] for _, _, cs in part for c in cs),
                                *(work[int(sid[1:]) - 1][0]["privacy_class"] for sid, _, _ in part))
        got = judge(part, privacy_class=cls, budget=budget)
        out["decisions"] += 1
        for sid, _, _ in part:
            v, tgt, conf = got[sid]
            verdicts[int(sid[1:]) - 1] = (v, tgt, conf, f"decision:{NEED}")
    changed = []
    for i, (r, st, cands) in enumerate(work):
        v, tgt, conf, by = verdicts[i]
        with connection() as conn:
            gate = Gate(conn, generation="g1", tag=tag, segment=None)
            s = gate._row(r["item_id"])
            target = next((c for c in cands if c["item_id"] == tgt), None) if tgt else None
            t = gate._row(target["item_id"]) if target else None
            if s is None or s["status"] not in LIVE or (t is not None and t["status"] not in LIVE):
                out["skipped"] += 1           # changed meanwhile (live extraction): a later pass sees the new state
                continue
            verdict, note = guard(st, v, target, conf, float(rc["min_confidence"]))
            res = relate(gate, {**r, "epistemic": s["epistemic"], "status": s["status"], "attributes": s["attributes"]},
                         st, verdict, target and {**target, "epistemic": t["epistemic"], "status": t["status"],
                                                  "attributes": t["attributes"]},
                         key=f"rr:{r['item_id']}", meta={"verdict": v, "decided_by": by, "confidence": conf}, note=note)
            changed += gate.changed
        out["items"] += 1
        out["ops"][res["op"]] = out["ops"].get(res["op"], 0) + 1
    if changed:
        try:
            search.reindex_derived(sorted(set(changed)))
            from . import consolidate
            consolidate.invalidate(item_ids=sorted(set(changed)))
        except Exception as e:  # noqa: BLE001 — derived: the index and views catch up
            log.warning("reindex / views after reconciliation failed: %s", e)
    with connection() as conn:
        out["remaining"] = len(_pending_existing(conn, 100000, only))
    return out


# ───────────────────────────── Run Plane ─────────────────────────────
def runplane(gate: Gate, source: str | None, thread_id: str) -> list[dict]:
    """Goals of this thread carried by a Run Plane objective follow it (proof level « runplane », never « verified »):
    the objective is the one already linked (attributes.task_id), else the one whose runs (origin or any attempt,
    runs.task_runs) started within ±5 min of the owner's request in the same session. A done objective marks the work
    executed (« terminé selon le Run Plane », an agent's claim, not a proof) and closes a goal already verified; a
    failed or cancelled one (the Run Plane cancels on interruption, never for the owner) records a step, the goal
    keeps its stage. Called by the extraction of the thread and, when an objective changes
    later, by the bus (task.ended / task.updated → assimilation « goals.runplane »)."""
    conn, out = gate.conn, []
    goals = conn.execute(f"""select item_id::text, kind, stage, attributes, generation,
                                   (select min(e.occurred_at) from core.events e where e.event_id = any(d.source_event_ids)
                                      and e.event_type = 'message.sent') as asked_at
                            from core.derived_items d where derived_by = %s and status = any(%s) and kind = 'goal'
                              and (valid_to is null or valid_to > now()) and generation = %s
                              and source_refs->>'thread' = %s {"and source_refs->>'source' = %s" if source else ""}
                              and coalesce(stage, '') <> all(%s)""",
                         (PROCESSOR, list(LIVE), gate.generation, thread_id, *([source] if source else []),
                          list(CLOSED))).fetchall()
    for g in goals:
        a0 = g["attributes"] or {}
        t = None
        if a0.get("task_id"):       # linked before: by its origin run unless recorded otherwise
            t = conn.execute("""select task_id::text, status, ended_at, last_outcome, %s as role from runs.tasks
                                where task_id::text = %s""", (a0.get("task_role") or "origin", a0["task_id"])).fetchone()
        if t is None and g["asked_at"]:
            t = conn.execute("""select t.task_id::text, t.status, t.ended_at, t.last_outcome,
                                       case when tr.run_id = t.run_id or tr.role = 'origin' then 'origin'
                                            else 'attempt' end as role
                                from runs.tasks t join runs.task_runs tr on tr.task_id = t.task_id
                                join runs.runs r on r.run_id = tr.run_id
                                where t.kind = 'objective'
                                  and (r.origin->>'session_id' like %s or r.origin->>'session_id' = %s)
                                  and r.started_at between %s - interval '5 minutes' and %s + interval '5 minutes'
                                order by (tr.role = 'origin') desc, abs(extract(epoch from r.started_at - %s)) limit 1""",
                             (f"%/{thread_id}", thread_id, g["asked_at"], g["asked_at"], g["asked_at"])).fetchone()
        if t is None and g["asked_at"]:      # older objectives not recorded in task_runs: their origin run
            t = conn.execute("""select t.task_id::text, t.status, t.ended_at, t.last_outcome, 'origin' as role
                                from runs.tasks t join runs.runs r on r.run_id = t.run_id
                                where (r.origin->>'session_id' like %s or r.origin->>'session_id' = %s)
                                  and r.started_at between %s - interval '5 minutes' and %s + interval '5 minutes'
                                order by abs(extract(epoch from r.started_at - %s)) limit 1""",
                             (f"%/{thread_id}", thread_id, g["asked_at"], g["asked_at"], g["asked_at"])).fetchone()
        if not t:
            continue
        a = dict(a0)
        a["task_id"] = t["task_id"]
        a["task_status"] = t["status"]
        a["task_role"] = t["role"]
        new = None
        # only the request that opened the objective follows its end: a request made while the objective went on
        # (a later run of it) is part of it, but its own completion is not shown by the objective's
        if t["status"] == "done" and t["role"] == "origin":
            new = "done" if g["stage"] == "verified" else ("executed" if ORDER.get(g["stage"] or "", 0) < 3 else None)
        elif t["status"] in ("failed", "cancelled") and t["role"] == "origin":
            # the Run Plane cancels an objective when its run is interrupted (tool error, engine restart, a newer
            # message): never the owner abandoning it — the goal keeps its stage, the interruption is a step
            steps = list(a.get("progress") or [])
            if not steps or steps[-1].get("act") != "runplane":
                why = ((t.get("last_outcome") or {}).get("reason") or "")[:80]
                steps.append({"at": str(t["ended_at"] or datetime.now(timezone.utc)), "act": "runplane",
                              "stage": g["stage"], "text": ("tâche Run Plane en échec" if t["status"] == "failed"
                                                            else "tâche Run Plane interrompue") + (f" : {why}" if why else "")})
                a["progress"] = steps[-12:]
        fields = {"attributes": a} | ({"stage": new} if new else {})
        if a == a0 and not new:
            continue
        res = gate.change(g["item_id"], fields, op="advance" if new else "link",
                          key=f"runplane:{g['item_id']}:{t['task_id']}:{t['status']}:{t['role']}", decided_by="runplane",
                          proof={"level": "runplane", "task": t["task_id"], "status": t["status"]},
                          reason=f"task {t['status']}")
        out.append({"item": g["item_id"], "task": t["task_id"], "stage": new, "result": res})
    return out


def runplane_task(task_id: str) -> dict:
    """An objective changed (bus): the goals of every thread its runs belong to follow it."""
    from . import search
    with connection() as conn:
        sessions = [r["s"] for r in conn.execute("""select distinct r.origin->>'session_id' s from runs.runs r
            where r.run_id in (select run_id from runs.task_runs where task_id::text = %s
                               union select run_id from runs.tasks where task_id::text = %s)""",
                                                (task_id, task_id)) if r["s"]]
        gate = Gate(conn, generation="g1", tag=None, segment=None, where="runplane")
        done = []
        for sid in sessions:
            done += runplane(gate, None, sid.rsplit("/", 1)[-1])
    if gate.changed:
        try:
            search.reindex_derived(sorted(set(gate.changed)))
        except Exception as e:  # noqa: BLE001
            log.warning("reindex after runplane failed: %s", e)
    return {"task": task_id, "sessions": len(sessions), "goals": len(done)}


class _DryRun(Exception):
    """Leaves a connection() block without committing (a dry run): carries what would have been done."""


def runplane_backfill(*, apply: bool = False) -> dict:
    try:
        return _runplane_backfill(apply)
    except _DryRun as d:
        return d.args[0]


def _runplane_backfill(apply: bool) -> dict:
    """The goals already recorded: every thread with an open goal and Run Plane runs in its session, once."""
    from . import search
    with connection() as conn:
        threads = [r["th"] for r in conn.execute("""select distinct d.source_refs->>'thread' th from core.derived_items d
            where d.derived_by = %s and d.generation = 'g1' and d.kind = 'goal' and d.status = any(%s)
              and (d.valid_to is null or d.valid_to > now()) and coalesce(d.stage, '') <> all(%s)
              and exists (select 1 from runs.runs r where r.origin->>'session_id' like '%%/' || (d.source_refs->>'thread'))""",
                                                   (PROCESSOR, list(LIVE), list(CLOSED)))]
        out = {"threads": len(threads), "goals": 0, "stages": {}, "executed": apply}
        gate = Gate(conn, generation="g1", tag=f"runplane-{datetime.now(timezone.utc):%Y-%m-%d}", segment=None,
                    where="runplane")
        for th in threads:
            for r in runplane(gate, None, th):
                out["goals"] += 1
                out["stages"][r["stage"] or "link"] = out["stages"].get(r["stage"] or "link", 0) + 1
        if not apply:
            raise _DryRun(out)
    if gate.changed:
        try:
            search.reindex_derived(sorted(set(gate.changed)))
        except Exception as e:  # noqa: BLE001
            log.warning("reindex after runplane backfill failed: %s", e)
    return out


# ───────────────────────────── revert and history ─────────────────────────────
def revert(tag: str, *, confirm: bool = False) -> dict:
    """Undo every change of a tagged run, newest first, field by field: a field still as this run left it gets its
    former value back; a field changed since by someone else keeps that change (only this run's own part is removed:
    its evidence events, its attribute keys). Items it created are retracted; provenance rows it added are deleted.
    Staged changes (never applied) are only marked. Dry run unless confirm."""
    with connection() as conn:
        rows = conn.execute("""select * from core.derived_changes where tag = %s and reverted_at is null
                               order by change_id desc""", (tag,)).fetchall()
        out = {"tag": tag, "changes": len(rows), "created": sum(r["op"] == "create" for r in rows),
               "staged": sum(r["staged"] for r in rows), "restored": 0, "kept_later_edits": 0, "executed": confirm}
        if not confirm:
            return out
        touched = []
        for ch in rows:
            if ch["staged"]:
                pass
            elif ch["op"] == "create":
                conn.execute("""update core.derived_items set status = 'retracted', valid_to = coalesce(valid_to, now()),
                                  attributes = attributes || jsonb_build_object('retracted_by', 'knowledge.revert', 'tag', %s::text)
                                where item_id = %s""", (tag, ch["item_id"]))
                conn.execute("""update search.chunks set hidden = true, hidden_reason = 'knowledge_revert'
                                where kind = 'derived' and ref_id = %s""", (ch["item_id"],))
            else:
                cur = conn.execute(f"select {', '.join(FIELDS)} from core.derived_items where item_id = %s for update",
                                   (ch["item_id"],)).fetchone()
                before, after = ch["before"] or {}, ch["after"] or {}
                sets, args = [], []
                for k, b in before.items():
                    now_v, a = _j(cur[k]), after.get(k)
                    if k == "source_event_ids":
                        added = set(a or []) - set(b or [])
                        v = sorted(set(now_v or []) - added) if added else now_v
                        if v != now_v:
                            sets.append("source_event_ids = %s::uuid[]"); args.append(v)
                    elif k == "attributes":
                        v = dict(now_v or {})
                        for kk in set(b or {}) | set(a or {}):
                            if (b or {}).get(kk) == (a or {}).get(kk):
                                continue
                            if v.get(kk) == (a or {}).get(kk):
                                if kk in (b or {}):
                                    v[kk] = b[kk]
                                else:
                                    v.pop(kk, None)
                            else:
                                out["kept_later_edits"] += 1
                        if v != now_v:
                            sets.append("attributes = %s::jsonb"); args.append(json.dumps(v, ensure_ascii=False))
                    elif now_v == a:
                        sets.append(f"{k} = %s" + ("::uuid" if k == "lineage_id" else "")); args.append(b)
                    elif now_v != b:
                        out["kept_later_edits"] += 1
                if sets:
                    conn.execute(f"update core.derived_items set {', '.join(sets)} where item_id = %s",
                                 (*args, ch["item_id"]))
                    out["restored"] += 1
            for p in ch["provenance"] or []:
                conn.execute("""delete from core.provenance where target_table = 'derived_items' and target_id = %s
                                and source_type = %s and source_id = %s and role = %s""",
                             (p["target"], p["source_type"], p["source"], p["role"]))
            # the key is freed (kept, suffixed): a replay after an undo writes again instead of being taken for done
            conn.execute("""update core.derived_changes set reverted_at = now(), key = key || ':reverted:' || change_id
                            where change_id = %s""", (ch["change_id"],))
            touched.append(str(ch["item_id"]))
    try:
        from . import search
        search.reindex_derived(sorted(set(touched)))
    except Exception as e:  # noqa: BLE001 — the index is derived: rebuildable
        log.warning("reindex after revert failed: %s", e)
    return out


def history(item_id: str) -> dict:
    """A piece of knowledge through time: every version of its lineage (current or not) and every change made to
    them, oldest first, with verdict, decider and proof."""
    with connection() as conn:
        lin = conn.execute("select coalesce(lineage_id, item_id)::text as l from core.derived_items where item_id = %s",
                           (item_id,)).fetchone()
        if not lin:
            return {"item": item_id, "versions": [], "changes": []}
        versions = conn.execute("""select item_id::text, kind, content, status, stage, epistemic, scope, generation,
                                          valid_from, valid_to, attributes->>'version' as version,
                                          attributes->>'superseded_by' as superseded_by
                                   from core.derived_items where lineage_id = %s::uuid or item_id = %s::uuid
                                   order by coalesce(valid_from, created_at)""", (lin["l"], lin["l"])).fetchall()
        ids = [v["item_id"] for v in versions]
        changes = conn.execute("""select change_id, at, item_id::text, op, verdict, decided_by, confidence, tag, staged,
                                         reason, proof, reverted_at is not null as reverted
                                  from core.derived_changes where item_id = any(%s::uuid[]) order by change_id""",
                               (ids,)).fetchall()
    return {"item": item_id, "lineage": lin["l"], "versions": versions, "changes": changes}
