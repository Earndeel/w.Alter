"""Continuous learning (P10.7): the judged truth grows every night, so the retriever keeps improving on its own.

judge_new_cases(): recent real messages (any runtime) that came with skill reads or skill injections → candidates =
live top-15 ∪ skills actually opened → Claude Haiku 5.5 labels each candidate 0/1/2 (same rubric as the benchmark) →
index/judged/auto-<date>.jsonl, used by the next `train`. cloud_allowed messages only (secret-masked), capped per
night, through walter_memory.llm (budget + ledger).
"""
from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import cards as cards_mod
from . import engine, history, store

sys.path.insert(0, "/opt/walter-memory")
from walter_memory import llm  # noqa: E402
from walter_memory.logs import mask  # noqa: E402

JUDGED = store.ROOT / "index" / "judged"
STATE = JUDGED / "state.json"
MODEL = "anthropic/claude-haiku-5.5"  # poste skills.judge (same family as the benchmark judges)
RUBRIC = """You are a relevance judge for W.Alter's skill library (procedures an AI agent loads before acting). The
user is "Monsieur" (French). For EVERY candidate skill, label how much the agent should load it to handle the CURRENT
user message (take the previous turn into account for short follow-ups):
2 = should load it: it directly covers the task, service, tool or problem at hand
1 = partially relevant / useful support, not needed
0 = not relevant
Several can be 2. If the message needs no procedure (chit-chat, thanks, personal talk), use only 0/1. Judge on
meaning, not word overlap. Return JSON only: {"labels": {"<candidate name>": 0|1|2, ...}} with every candidate."""


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def judged_ids() -> set[str]:
    return set(engine.judged_labels())


def judge_new_cases(max_cases: int = 60, days: int = 3, workers: int = 6) -> dict:
    JUDGED.mkdir(parents=True, exist_ok=True)
    os.chmod(JUDGED, 0o700)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    e = engine.load_engine()
    done = judged_ids()
    cases = [c for c in history.cases(e.aliases, since=since, negatives=True)  # with AND without skill reads
             if c["privacy_class"] == "cloud_allowed" and c["qid"] not in done
             and not any(m in c["query"][:200] for m in ("[ASYNC DELEGATION", "[CONTEXT COMPACTION", "<task-notification",
                                                          "[SYSTEM NOTIFICATION", "Another Claude session"))]
    cases = sorted(cases, key=lambda c: -c["ts"])[:max_cases]
    desc = {s["name"]: s["description"] for s in e.skills}

    def one(c):
        top = [r["name"] for r in e.search(c["query"], c["ctx"], session=c.get("session_skills"), k=15)]
        cand = [n for n in dict.fromkeys(c["gold"] + top) if n in desc]
        lines = "\n".join(f"- {n}: {((cards_mod.load(n) or {}).get('summary') or desc[n])[:200]}" for n in sorted(cand))
        prompt = (f"{RUBRIC}\n\n[previous turn]\n{mask(c['ctx'][-800:])}\n\n[current user message]\n"
                  f"{mask(c['query'][:1500])}\n\n[candidate skills, alphabetical]\n{lines}")
        try:
            r = llm.chat([{"role": "user", "content": prompt}], model=MODEL, processor="skills.judge.auto",
                         privacy_class="cloud_allowed", budget="recurring", timeout=90, purpose="judge new case")
            m = re.search(r"\{.*\}", r["content"], re.S)
            labels = json.loads(m.group(0))["labels"] if m else None
        except Exception:
            return None
        if not isinstance(labels, dict):
            return None
        labels = {n: int(v) for n, v in labels.items() if n in cand and str(v) in ("0", "1", "2")}
        return {"id": c["qid"], "labels": labels, "source": "auto", "at": datetime.now(timezone.utc).isoformat(),
                "runtime": c["id"].split("/")[0]} if labels else None

    out = JUDGED / f"auto-{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    n = 0
    with ThreadPoolExecutor(workers) as ex, open(out, "a") as f:
        for res in ex.map(one, cases):
            if res:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                n += 1
    os.chmod(out, 0o600)
    st = _state() | {"last_run": datetime.now(timezone.utc).isoformat(), "last_judged": n,
                     "total_judged": len(judged_ids())}
    STATE.write_text(json.dumps(st, indent=1))
    return {"candidates": len(cases), "judged": n, "total_judged": st["total_judged"], "file": out.name}


# ───────────────────────────── learner: drafts from sessions ─────────────────────────────

LEARN_STATE = store.ROOT / "index" / "learner.json"
SKIP_PLATFORMS = ("cron", "subagent", "oneshot", "curator", "prod_validation")


def _session_digest(conn, session_id: str, limit: int = 22000) -> str:
    rows = conn.execute("""select type, tool, text, status from walter_logs.events where session_id = %s
                           and type in ('user/message', 'assistant/message', 'tool/call', 'tool/result')
                           order by seq""", (session_id,)).fetchall()
    parts = []
    for r in rows:
        txt = mask(r["text"] or "")
        if r["type"] == "user/message":
            parts.append(f"[USER] {txt[:1200]}")
        elif r["type"] == "assistant/message":
            parts.append(f"[ASSISTANT] {txt[:800]}")
        elif r["type"] == "tool/call":
            parts.append(f"[CALL {r['tool']}] {txt[:400]}")
        elif r["status"] not in (None, "ok") or any(k in txt[:3000] for k in ("Traceback", "Error", "error:", "failed")):
            parts.append(f"[RESULT {r['tool']} {r['status'] or ''}] {txt[:500]}")
    text = "\n".join(parts)
    return text if len(text) <= limit else text[:limit // 3] + "\n[…]\n" + text[-2 * limit // 3:]


def mine_sessions(max_sessions: int = 3, hours: int = 48) -> dict:
    """Recent busy sessions (≥ 12 tool calls, ≤ 1 skill read, cloud_allowed) → the editor proposes a new skill or a
    patch of an existing one, or nothing → drafts/ via the write door → judged by the curator at night."""
    from . import models, proposals
    sys.path.insert(0, "/opt/walter-memory")
    from walter_memory.db import connection
    st = json.loads(LEARN_STATE.read_text()) if LEARN_STATE.exists() else {"seen": []}
    seen = set(st.get("seen", []))
    with connection() as conn:
        cands = conn.execute(
            """select s.session_id, s.runtime, s.platform, s.title,
                      count(*) filter (where e.type = 'tool/call') as calls,
                      count(*) filter (where e.type = 'tool/call' and e.tool in ('skill_view', 'mcp__walter__skill_read',
                                                                                  'walter_skill_read', 'Skill')) as reads,
                      count(*) filter (where e.type = 'user/message') as users
               from walter_logs.sessions s join walter_logs.events e using (session_id)
               where s.last_event_at > now() - make_interval(hours => %s) and s.privacy_class = 'cloud_allowed'
                 and coalesce(s.platform, '') <> all(%s)
               group by 1, 2, 3, 4 having count(*) filter (where e.type = 'tool/call') >= 12
               order by calls desc limit 20""", (hours, list(SKIP_PLATFORMS))).fetchall()
        cands = [c for c in cands if c["session_id"] not in seen and c["reads"] <= 1 and c["users"] >= 1][:max_sessions]
        digests = {c["session_id"]: _session_digest(conn, c["session_id"]) for c in cands}
    out = {"sessions": len(cands), "proposed": [], "patched": [], "skipped": [], "refused": []}
    if not cands or not models.codex_ready():
        return out | {"note": "nothing to mine" if not cands else "editor unavailable"}
    e = engine.load_engine()
    for c in cands:
        dig = digests[c["session_id"]]
        first_user = next((l[7:] for l in dig.splitlines() if l.startswith("[USER] ")), c["title"] or "")
        related = e.search(first_user[:1500], k=8)
        rel = "\n".join(f"- {r['name']}: {r['summary'][:180]}" for r in related)
        prompt = (
            "You are the learner of W.Alter's skill library (procedures an AI agent loads before acting, on "
            "Monsieur's VM). Read this agent session digest. Decide whether it taught a REUSABLE procedure that the "
            "library lacks (several steps, exact commands/paths/checks, pitfalls found the hard way). Existing related "
            f"skills:\n{rel}\n\nAnswer with JSON only, one of:\n"
            '{"action": "skip", "reason": "..."}\n'
            '{"action": "patch", "target": "<existing skill name>", "section": "<markdown section to append, starting '
            'with ## , imperative rules, exact commands>", "reason": "<what it adds + evidence from the session>"}\n'
            '{"action": "new", "name": "<kebab-case>", "domain": "<devops|productivity|media|research|...>", '
            '"skill_md": "<full SKILL.md: frontmatter name + description starting with Use when, then rules>", '
            '"reason": "<recurring task + evidence>"}\n'
            "Prefer skip over a weak skill; prefer patch over a near-duplicate new skill. Never include secret "
            f"values, personal data or one-off narration.\n\nSESSION ({c['runtime']}/{c['platform']}, "
            f"{c['calls']} tool calls):\n{dig}")
        res = models.parse_json(models.editor(prompt, effort="medium"))
        seen.add(c["session_id"])
        if not res or res.get("action") == "skip":
            out["skipped"].append({"session": c["session_id"], "reason": (res or {}).get("reason", "no answer")[:200]})
            continue
        try:
            if res.get("action") == "new":
                r = proposals.propose(res["name"], res["skill_md"], res.get("reason", "") + f" [session {c['session_id']}]",
                                      domain=res.get("domain", ""), runtime="learner", session_id=c["session_id"])
                out["proposed"].append({"name": res["name"], "draft": r["draft"]})
            elif res.get("action") == "patch" and res.get("target"):
                s = store.find(res["target"], include_archived=False)
                if s is None:
                    raise proposals.Refused(f"unknown target {res['target']}")
                new_md = s.body.rstrip() + "\n\n" + res.get("section", "").strip() + "\n"
                r = proposals.patch(res["target"], res.get("reason", "") + f" [session {c['session_id']}]",
                                    skill_md=new_md, runtime="learner", session_id=c["session_id"])
                out["patched"].append({"target": res["target"], "draft": r["draft"]})
        except (proposals.Refused, KeyError) as ex:
            out["refused"].append({"session": c["session_id"], "why": str(ex)[:200]})
    st["seen"] = sorted(seen)[-2000:]
    LEARN_STATE.write_text(json.dumps(st))
    return out
