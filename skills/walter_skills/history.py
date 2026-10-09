"""What the skills were actually used for: (message, previous turn, skills opened, skills opened earlier in the session)
from walter_logs, every runtime that reports skill reads. This is the learner's raw material (learned triggers, usage
prior, fusion training). Same extraction as bench/build_dataset.py, without the benchmark split.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime

sys.path.insert(0, "/opt/walter-memory")
from walter_memory.db import connect  # noqa: E402

HUMAN_PLATFORMS = ("desktop", "tui", "cli", "telegram", "voice-router")
SKILL_TOOLS = ("skill_view", "mcp__walter__skill_read")


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
        key = hashlib.sha1(re.sub(r"\s+", " ", q.lower())[:500].encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        c["qid"] = key[:12]  # same key as the benchmark / judged labels
        keep.append(c)
    return keep


def session_history(session_id: str, aliases: dict[str, str]) -> dict[str, int]:
    """Skills read earlier in a live session (any runtime): name -> turns ago (0 = previous turn)."""
    conn = connect()
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
