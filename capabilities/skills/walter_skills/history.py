"""What the skills were actually used for: (message, previous turn, skills opened, skills opened earlier in the session)
from walter_logs, every runtime that reports skill reads. This is the learner's raw material (learned triggers, usage
prior, fusion training). Same extraction as bench/build_dataset.py, without the benchmark split.
"""
from __future__ import annotations

import json
from datetime import datetime

from walter_memory.db import connect

from .registry import qid as _qid

HUMAN_PLATFORMS = ("desktop", "tui", "cli", "telegram", "voice-router")
SKILL_TOOLS = ("skill_view", "mcp__walter__skill_read", "walter_skill_read", "Skill")
SEARCH_TOOLS = ("mcp__walter__skills_search", "walter_skill_search", "skills_list")


def cases(aliases: dict[str, str], since: str | None = None, negatives: bool = False) -> list[dict]:
    """aliases: any name a runtime may use (dir name, frontmatter name) -> store name."""
    conn = connect()
    rows = conn.execute(
        """select e.session_id, e.seq, e.type, e.occurred_at, e.tool, e.text, e.privacy_class
           from walter_logs.events e join walter_logs.sessions s using (session_id)
           where (s.runtime <> 'hermes' or s.platform = any(%s))
             and (%s::timestamptz is null or e.occurred_at >= %s::timestamptz)
             and (e.type in ('user/message', 'assistant/message') or (e.type = 'tool/call' and e.tool = any(%s)))
           order by e.session_id, e.seq""", (list(HUMAN_PLATFORMS), since, since, list(SKILL_TOOLS))).fetchall()
    out, cur = [], None
    prev_user, prev_assistant, prev_session, turn, opened = "", "", None, 0, {}
    for r in rows:
        if r["session_id"] != prev_session:
            prev_user, prev_assistant, prev_session, turn, opened = "", "", r["session_id"], 0, {}
        if r["type"] == "assistant/message":
            prev_assistant = (r["text"] or prev_assistant).strip()
            continue
        if r["type"] == "user/message":
            if cur is not None and cur["session_id"] == r["session_id"]:
                prev_user = cur["query"]
            cur = {"session_id": r["session_id"], "ts": r["occurred_at"].timestamp(), "id": f"{r['session_id']}#{r['seq']}",
                   "privacy_class": r["privacy_class"], "query": (r["text"] or "").strip()[:1500], "gold": [],
                   "ctx": f"{prev_user[-400:]}\n{prev_assistant[-300:]}".strip(),
                   "session_skills": {n: turn - t for n, t in opened.items()}}
            turn += 1
            prev_assistant = ""
            out.append(cur)
            continue
        if cur is None or cur["session_id"] != r["session_id"]:
            continue
        try:
            args = json.loads(r["text"] or "{}")
        except json.JSONDecodeError:
            continue
        if args.get("file_path"):
            continue
        name = aliases.get(str(args.get("name", "")).strip())
        if name:
            if name not in cur["gold"]:
                cur["gold"].append(name)
            opened[name] = turn
    keep, seen = [], set()
    for c in out:
        q = c["query"]
        if (not c["gold"] and not negatives) or q.startswith("/") or len(q.split()) < 3 \
                or q.startswith(("[System", "[SYSTEM", "<system")):
            continue
        key = _qid(q)  # same key as the benchmark and every label
        if key in seen:
            continue
        seen.add(key)
        c["qid"] = key
        keep.append(c)
    return keep


def session_history(session_id: str, aliases: dict[str, str]) -> dict[str, int]:
    """Skills read earlier in a live session (any runtime): name -> turns ago (0 = previous turn)."""
    from .registry import db
    with db() as conn:  # pooled + circuit breaker: called on every live request
        rows = conn.execute(
            """select e.type, e.text from walter_logs.events e
               where e.session_id = %s and (e.type = 'user/message' or (e.type = 'tool/call' and e.tool = any(%s)))
               order by e.seq""", (session_id, list(SKILL_TOOLS))).fetchall()
    turn, opened = 0, {}
    for r in rows:
        if r["type"] == "user/message":
            turn += 1
            continue
        try:
            name = aliases.get(str(json.loads(r["text"] or "{}").get("name", "")).strip())
        except json.JSONDecodeError:
            continue
        if name:
            opened[name] = turn
    return {n: max(0, turn - t) for n, t in opened.items()}


def now_ts() -> float:
    return datetime.now().timestamp()


def reads_after(session_id: str, since, until, aliases: dict[str, str]) -> tuple[list[str], list[str]]:
    """(skills opened, searches made) by the agent in a session between two instants — the implicit feedback."""
    from .registry import db
    opened, searched = [], []
    with db() as conn:
        rows = conn.execute(
            """select tool, text from walter_logs.events where session_id = %s and type = 'tool/call'
               and occurred_at >= %s and occurred_at < %s and tool = any(%s) order by seq""",
            (session_id, since, until, list(SKILL_TOOLS + SEARCH_TOOLS))).fetchall()
    for r in rows:
        try:
            a = json.loads(r["text"] or "{}")
        except json.JSONDecodeError:
            continue
        if r["tool"] in SEARCH_TOOLS:
            searched.append(str(a.get("query") or a.get("category") or ""))
        elif not a.get("file_path"):
            n = aliases.get(str(a.get("name") or a.get("skill") or "").strip())
            if n and n not in opened:
                opened.append(n)
    return opened, searched
