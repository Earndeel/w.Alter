"""Hermes baseline: an LLM reads Hermes' skill index (names + descriptions cut to 57 chars, grouped by category, same
header as Hermes' system prompt) plus the conversation, and names the skills it would load with skill_view.

Sample = every cloud_allowed test case + N random dev cases. Through walter_memory.llm (privacy + budget guard).
Writes data/llm_<corpus>_<tag>.jsonl (resumable). Usage: python hermes_llm.py --corpus active|full [--dev 100]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/opt/walter-memory")
from walter_memory import llm  # noqa: E402

from evaluate import DATA, hermes_desc, load  # noqa: E402

HEADER = ("## Skills\nBefore replying, scan the skills below. If a skill matches or is even partially relevant to your "
          "task, you MUST load it with skill_view(name) and follow its instructions. Err on the side of loading.\n")
ASK = ("You are the agent described above. Given the conversation below, list the skills you would load with "
       "skill_view before answering, most relevant first (at most 5; [] if none). Answer with JSON only: "
       '{"skills": ["name", ...]}')


def index(corpus: list[dict]) -> str:
    groups = defaultdict(list)
    for s in sorted(corpus, key=lambda s: s["name"]):
        groups[(s["category"] or "other").split("/")[0]].append(s)
    lines = [HEADER, "<available_skills>"]
    for cat in sorted(groups):
        lines.append(f"  {cat}:")
        lines += [f"    - {s['name']}: {hermes_desc(s['description'])}" for s in groups[cat]]
    lines.append("</available_skills>")
    return "\n".join(lines)


def sample(cases: list[dict], n_dev: int) -> list[dict]:
    ok = [c for c in cases if c["privacy_class"] == "cloud_allowed"]
    dev = [c for c in ok if c["split"] == "dev"]
    random.Random(7).shuffle(dev)
    return [c for c in ok if c["split"] == "test"] + dev[:n_dev]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="active")
    ap.add_argument("--dev", type=int, default=100)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--session", action="store_true", help="also tell the model which skills were loaded earlier")
    ap.add_argument("--ids", default="", help="file of case ids to run instead of the benchmark sample")
    ap.add_argument("--tag", default="", help="suffix for the output file")
    a = ap.parse_args()
    cases, corpus = load()
    if a.corpus == "active":
        corpus = [s for s in corpus if not s["archived"]]
    names = {s["name"] for s in corpus}
    system = index(corpus)
    tag = a.model.split("/")[-1]
    out = DATA / f"llm_{a.corpus}_hermes-index{'+session' if a.session else ''}_{tag}{a.tag}.jsonl"
    done = {json.loads(line)["id"] for line in open(out)} if out.exists() else set()
    if a.ids:
        ids = set(open(a.ids).read().split())
        todo = [c for c in cases if c["id"] in ids and c["id"] not in done]
    elif out.name.startswith("llm_full_") or "+session" in out.name:  # same case sample as the first run
        ids = {json.loads(line)["id"] for line in open(DATA / "llm_active_hermes-index_gpt-6-luna.jsonl")}
        todo = [c for c in cases if c["id"] in ids and c["id"] not in done]
    else:
        todo = [c for c in sample(cases, a.dev) if c["id"] not in done]
    print(f"{len(todo)} to run, index {len(system)} chars", file=sys.stderr)

    def run(c: dict):
        ctx = c.get("context") or {}
        convo = (f"[previous user message]\n{ctx.get('prev_user', '')}\n[previous assistant message]\n"
                 f"{ctx.get('prev_assistant', '')}\n[current user message]\n{c['query']}")
        if a.session and c.get("session_skills"):
            loaded = sorted(c["session_skills"], key=c["session_skills"].get)
            convo = f"[skills already loaded earlier in this conversation, most recent first]\n{', '.join(loaded)}\n" + convo
        t0 = time.perf_counter()
        try:
            r = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": f"{convo}\n\n{ASK}"}],
                         model=a.model, processor="bench.skills.hermes_llm", privacy_class=c["privacy_class"],
                         budget="backfill", purpose=f"walter-skills baseline {a.corpus}", timeout=120,
                         reasoning={"effort": "low"})
        except Exception as e:  # noqa: BLE001
            print("ERR", c["id"], str(e)[:200], file=sys.stderr)
            return None
        m = re.search(r"\{.*\}", r["content"], re.S)
        try:
            ranked = [s for s in json.loads(m.group(0))["skills"] if s in names] if m else []
        except (json.JSONDecodeError, KeyError, TypeError):
            ranked = []
        return {"id": c["id"], "ranked": ranked, "latency_ms": round(1000 * (time.perf_counter() - t0)),
                "cost_usd": r.get("cost_usd")}

    with ThreadPoolExecutor(a.workers) as ex, open(out, "a") as f:
        for res in ex.map(run, todo):
            if res:
                f.write(json.dumps(res) + "\n")
                f.flush()
    rows = [json.loads(line) for line in open(out)]
    print(f"{len(rows)} rows, cost {sum(r['cost_usd'] or 0 for r in rows):.3f} USD", file=sys.stderr)


if __name__ == "__main__":
    main()
