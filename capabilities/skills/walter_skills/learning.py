"""The learning loop — one loop, every night:

  1. implicit()  the agent's own choices become labels (the model as judge, free and continuous):
                 shown then opened → 2 (implicit) · opened without being shown, after its own search → 2 (miss)
  2. judge()     a sample of recent real messages labelled by the judge poste (calibration + growing holdout)
  3. train()     a candidate ranker from history (learned triggers, prior) + all labels (fusion)
  4. promote()   candidate vs active on the holdout (single evaluator); promoted only if not worse
The service picks up a newly promoted ranker by itself (it polls the active version).
"""
from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import config, evaluate, history, postes, registry
from .ranker import Corpus, Encoder, train as train_ranker
from .retrieval import aliases, corpus_skills

JUDGE_RUBRIC = """You are a relevance judge for W.Alter's skill library (procedures an AI agent loads before acting). The
user is "Monsieur" (French). For EVERY candidate skill, label how much the agent should load it to handle the CURRENT
user message (take the previous turn into account for short follow-ups):
2 = should load it: it directly covers the task, service, tool or problem at hand
1 = partially relevant / useful support, not needed
0 = not relevant
Several can be 2. If the message needs no procedure (chit-chat, thanks, personal talk), use only 0/1. Judge on
meaning, not word overlap. Return JSON only: {"labels": {"<candidate name>": 0|1|2, ...}} with every candidate."""
MACHINE = ("[ASYNC DELEGATION", "[CONTEXT COMPACTION", "<task-notification", "[SYSTEM NOTIFICATION", "Another Claude session")


def _cases_by_qid(since: str | None = None) -> dict[str, dict]:
    return {c["qid"]: c for c in history.cases(aliases(), since=since, negatives=True)}


# 1 ── the model as judge ─────────────────────────────────────────────────────────────────────────────

def implicit(session_ids: list[str] | None = None) -> dict:
    """Read the journal of exposures back against what the agents then opened (walter_logs).

    session_ids given (bus: turn.ended / session.ended) → just those sessions, up to now; otherwise the nightly sweep
    from the watermark. Labels are upserts and only ever add what was opened, so a later pass is harmless."""
    cfg = config.get("learning")
    mark = registry.get_state("implicit_watermark", "2026-10-10T00:00:00+00:00")
    al = aliases()
    window = """select id, at, session_id, runtime, query_sha, injected,
                       lead(at) over (partition by session_id order by at) as next_at
                from skills.retrievals where mode = 'inject' and session_id is not null"""
    with registry.db() as c:
        if session_ids:
            rows = c.execute(window + " and session_id = any(%s) order by at", (list(session_ids),)).fetchall()
        else:
            rows = c.execute(window + " and at > %s and at < now() - interval '20 minutes' order by at",
                             (mark,)).fetchall()
    stats = Counter()
    last = mark
    now = datetime.now(timezone.utc)
    for r in rows:
        until = r["next_at"] or min(r["at"] + timedelta(minutes=30), now)
        opened, searched = history.reads_after(r["session_id"], r["at"], until, al)
        shown = set(r["injected"] or [])
        ev = {"retrieval": r["id"], "runtime": r["runtime"]}
        hit = {n: 2 for n in opened if n in shown}
        miss = {n: 2 for n in opened if n not in shown} if searched else {}
        stats["implicit"] += registry.put_labels(r["query_sha"], hit, "implicit", cfg["implicit_weight"], r["runtime"], ev)
        stats["miss"] += registry.put_labels(r["query_sha"], miss, "miss", cfg["miss_weight"], r["runtime"], ev)
        stats["exposures"] += 1
        last = r["at"].isoformat()
    if not session_ids:
        registry.set_state("implicit_watermark", last)
    return dict(stats)


# 2 ── sampled judge ──────────────────────────────────────────────────────────────────────────────────

def judge(max_cases: int | None = None, days: int = 3) -> dict:
    from .retrieval import engine
    max_cases = max_cases or config.get("learning")["judge_per_night"]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    done = registry.labelled_qids("judge") | registry.labelled_qids("bench")
    cases = [c for c in _cases_by_qid(since).values() if c["privacy_class"] == "cloud_allowed"
             and c["qid"] not in done and not any(m in c["query"][:200] for m in MACHINE)]
    cases = sorted(cases, key=lambda c: -c["ts"])[:max_cases]
    e = engine()

    def one(c):
        top = [r["name"] for r in e.rank(c["query"], c["ctx"], c.get("session_skills"), k=15)]
        cand = [n for n in dict.fromkeys(c["gold"] + top) if n in e.corpus.summary]
        lines = "\n".join(f"- {n}: {e.corpus.summary[n][:200]}" for n in sorted(cand))
        obj, route = postes.ask_json("judge", f"{JUDGE_RUBRIC}\n\n[previous turn]\n{c['ctx'][-800:]}\n\n[current user "
                                              f"message]\n{c['query'][:1500]}\n\n[candidate skills, alphabetical]\n{lines}",
                                     require="labels", timeout=120, processor="skills.judge.auto")
        labels = {n: int(v) for n, v in ((obj or {}).get("labels") or {}).items() if n in cand and str(v) in ("0", "1", "2")}
        return registry.put_labels(c["qid"], labels, "judge", 1.0, c["id"].split("/")[0], {"route": route}) if labels else 0

    with ThreadPoolExecutor(6) as ex:
        n = sum(1 for k in ex.map(one, cases) if k)
    return {"candidates": len(cases), "judged": n}


# 3-4 ── train a candidate, promote it if not worse ─────────────────────────────────────────────────────

def train_and_promote(force: bool = False) -> dict:
    t0 = time.time()
    cfg = config.get("learning")
    enc = Encoder.get()
    skills = corpus_skills()
    corpus = Corpus(skills, registry.cards(), enc)
    by_qid = _cases_by_qid()
    hist_cases = [c for c in by_qid.values() if c["gold"]]
    train_ex = evaluate.examples(by_qid, holdout=False)
    eval_ex = evaluate.examples(by_qid, holdout=True, sources=("bench", "judge"))
    cand = train_ranker(corpus, hist_cases, train_ex, enc.model_name)
    m_cand = evaluate.measure(corpus, cand, eval_ex)
    pol = config.get("policy")
    m_cand["confident_p1"] = evaluate.calibrate_confidence(corpus, cand, eval_ex, pol["k_confident"], pol["k_max"])
    version = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    active_row = registry.ranker()
    from .ranker import Ranker
    m_act = evaluate.measure(corpus, Ranker.loads(bytes(active_row["blob"])), eval_ex) if active_row else None
    tol = cfg["promote_tolerance"]
    ok = force or m_act is None or (m_cand["n"] >= min(cfg["eval_min_cases"], m_act["n"]) and
                                    m_cand["at15"] >= m_act["at15"] - tol and m_cand["at3"] >= m_act["at3"] - tol)
    metrics = {"candidate": m_cand, "active": m_act, "train_examples": len(train_ex), "history_cases": len(hist_cases),
               "labelled_messages": registry.label_counts(),
               "seconds": round(time.time() - t0)}
    registry.save_ranker(version, cand.dumps(), enc.model_name, config.get("retrieval")["learner"], len(skills), metrics)
    registry.set_ranker_state(version, "active" if ok else "rejected")
    registry.ledger("learning", "promote" if ok else "reject", version, None, metrics)
    return {"version": version, "promoted": ok, **metrics}


def nightly() -> dict:
    out = {}
    for name, fn in (("implicit", implicit), ("judge", judge), ("sessions", drafts_from_sessions),
                     ("train", train_and_promote)):
        try:
            out[name] = fn()
        except Exception as e:  # one failing step never blocks the next
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out



# 5 ── drafts from sessions (the library learns new procedures) ────────────────────────────────────────

SKIP_PLATFORMS = ("cron", "subagent", "oneshot", "curator", "prod_validation")


def _digest(session_id: str, limit: int = 22000) -> str:
    from walter_memory.logs import mask
    with registry.db() as c:
        rows = c.execute("""select type, tool, text, status from walter_logs.events where session_id = %s
                            and type in ('user/message', 'assistant/message', 'tool/call', 'tool/result')
                            order by seq""", (session_id,)).fetchall()
    parts = []
    for r in rows:
        t = mask(r["text"] or "")
        if r["type"] == "user/message":
            parts.append(f"[USER] {t[:1200]}")
        elif r["type"] == "assistant/message":
            parts.append(f"[ASSISTANT] {t[:800]}")
        elif r["type"] == "tool/call":
            parts.append(f"[CALL {r['tool']}] {t[:400]}")
        elif r["status"] not in (None, "ok") or any(k in t[:3000] for k in ("Traceback", "Error", "error:", "failed")):
            parts.append(f"[RESULT {r['tool']} {r['status'] or ''}] {t[:500]}")
    text = "\n".join(parts)
    return text if len(text) <= limit else text[:limit // 3] + "\n[…]\n" + text[-2 * limit // 3:]


def drafts_from_sessions(max_sessions: int | None = None, hours: int = 48, session_ids: list[str] | None = None) -> dict:
    """Busy recent sessions (≥ 12 tool calls, ≤ 1 skill read, cloud_allowed) → the editor proposes a new skill, a
    patch, or nothing → the write door (→ skill.proposed → judged within a minute).
    session_ids given (bus: session.ended) → only those; otherwise the nightly pass over the last `hours`."""
    from . import door, store
    from .retrieval import engine
    max_sessions = max_sessions or config.get("curation")["learner_sessions_per_night"]
    seen = set(registry.get_state("learner", {}).get("seen", []))
    with registry.db() as c:
        cands = c.execute(
            """select s.session_id, s.runtime, s.platform, s.title,
                      count(*) filter (where e.type = 'tool/call') as calls,
                      count(*) filter (where e.type = 'tool/call' and e.tool = any(%s)) as reads
               from walter_logs.sessions s join walter_logs.events e using (session_id)
               where s.last_event_at > now() - make_interval(hours => %s) and s.privacy_class = 'cloud_allowed'
                 and coalesce(s.platform, '') <> all(%s) and (%s::text[] is null or s.session_id = any(%s::text[]))
               group by 1, 2, 3, 4 having count(*) filter (where e.type = 'tool/call') >= 12
               order by calls desc limit 20""", (list(history.SKILL_TOOLS), hours if not session_ids else 24 * 30,
                                                 list(SKIP_PLATFORMS), session_ids, session_ids)).fetchall()
    cands = [x for x in cands if x["session_id"] not in seen and x["reads"] <= 1][:max_sessions]
    out = {"sessions": len(cands), "new": [], "patch": [], "skip": [], "refused": []}
    if not cands or not postes.available("editor"):
        return out
    e = engine()
    for x in cands:
        dig = _digest(x["session_id"])
        first = next((line[7:] for line in dig.splitlines() if line.startswith("[USER] ")), x["title"] or "")
        related = "\n".join(f"- {r['name']}: {r['summary'][:180]}" for r in e.rank(first[:1500], k=8))
        obj, _ = postes.ask_json("editor", (
            "You are the learner of W.Alter's skill library (procedures an AI agent loads before acting, on Monsieur's "
            "VM). Did this session teach a REUSABLE procedure the library lacks (several steps, exact commands, paths, "
            f"checks, pitfalls found the hard way)? Existing related skills:\n{related}\n\nAnswer JSON only, one of:\n"
            '{"action": "skip", "reason": "..."}\n'
            '{"action": "patch", "target": "<existing skill>", "section": "<## section to append: imperative rules, '
            'exact commands>", "reason": "<what it adds + evidence>"}\n'
            '{"action": "new", "name": "<kebab-case>", "domain": "<domain>", "skill_md": "<full SKILL.md, frontmatter '
            'name + description starting with Use when>", "reason": "<recurring task + evidence>"}\n'
            "Prefer skip over a weak skill and patch over a near-duplicate. No secret values, no personal data, no "
            f"narration.\n\nSESSION ({x['runtime']}/{x['platform']}, {x['calls']} tool calls):\n{dig}"), require="action")
        seen.add(x["session_id"])
        try:
            if not obj or obj["action"] == "skip":
                out["skip"].append({"session": x["session_id"], "reason": str((obj or {}).get("reason", "no answer"))[:200]})
            elif obj["action"] == "new":
                r = door.propose(obj["name"], obj["skill_md"], f"{obj.get('reason', '')} [session {x['session_id']}]",
                                 domain=obj.get("domain", ""), runtime="learner", session_id=x["session_id"])
                out["new"].append(r["draft"])
            elif obj["action"] == "patch":
                s = store.find(obj.get("target", ""), include_archived=False)
                if s is None:
                    raise door.Refused(f"unknown target {obj.get('target')}")
                r = door.patch(s.name, f"{obj.get('reason', '')} [session {x['session_id']}]",
                               skill_md=s.body.rstrip() + "\n\n" + str(obj.get("section", "")).strip() + "\n",
                               runtime="learner", session_id=x["session_id"])
                out["patch"].append(r["draft"])
        except (door.Refused, KeyError) as ex:
            out["refused"].append({"session": x["session_id"], "why": str(ex)[:200]})
    registry.set_state("learner", {"seen": sorted(seen)[-2000:]})
    return out
