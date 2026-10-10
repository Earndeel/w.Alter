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
