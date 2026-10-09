"""Second stage on the local shortlist (only the top-N of the walter retriever leaves the VM, as compact cards).

  cohere : cohere/rerank-4-fast over the shortlist cards (OpenRouter /rerank)
  llm    : a small LLM picks and orders the skills to load among the shortlist (same question Hermes' model answers,
           but on N cards instead of the whole index)
Input: a dump from train_judged.py / evaluate_walter.py. Output: data/<method>_<tag>.jsonl (same dump format).
Usage: python rerank_shortlist.py --dump data/walter_judged_hgb.jsonl --method llm --model openai/gpt-6-luna
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, "/opt/walter-memory")
sys.path.insert(0, "/opt/walter-skills")
from walter_memory import llm  # noqa: E402
from walter_skills import cards as cards_mod  # noqa: E402

from evaluate import DATA, load  # noqa: E402

ASK = ("Skills are procedural guides the agent loads before acting. Below: the conversation, then candidate skills "
       "(name — when to use — example requests). List the skills the agent should load to handle the CURRENT user "
       "message, most useful first (at most 5; [] if none applies). Prefer the specific skill over a generic one. "
       'Answer with JSON only: {"skills": ["name", ...]}')


def card_text(name: str, desc: str, rich: bool) -> str:
    c = cards_mod.load(name) or {}
    s = f"{name} — {c.get('summary') or desc[:160]}"
    if rich:
        ex = "; ".join((c.get("intents_fr") or [])[:3])
        s += f" | e.g. {ex}" if ex else ""
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--method", choices=["cohere", "llm"], required=True)
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--corpus", default="full")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    cases, corpus = load()
    by_id = {c["id"]: c for c in cases}
    desc = {s["name"]: s["description"] for s in corpus}
    rows = [json.loads(line) for line in open(a.dump)]
    rows = [r for r in rows if r["corpus"] == a.corpus and by_id[r["id"]]["privacy_class"] != "local_only"]
    rows = list({r["id"]: r for r in rows}.values())
    tag = a.model.split("/")[-1] if a.method == "llm" else "rerank-4-fast"
    out = DATA / f"{a.method}_{tag}_n{a.n}_{Path(a.dump).stem}.jsonl"
    done = {json.loads(line)["id"] for line in open(out)} if out.exists() else set()
    rows = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} to run -> {out.name}", file=sys.stderr)

    def one(r):
        c = by_id[r["id"]]
        ctx = c.get("context") or {}
        short = r["ranked"][:a.n]
        t0 = time.perf_counter()
        try:
            if a.method == "cohere":
                q = f"{ctx.get('prev_user', '')[-300:]}\n{c['query'][:1000]}"
                docs = [card_text(n, desc.get(n, ""), True) for n in short]
                resp = httpx.post("https://openrouter.ai/api/v1/rerank", timeout=20,
                                  headers={"Authorization": f"Bearer {llm._key()}"},
                                  json={"model": "cohere/rerank-4-fast", "query": q, "documents": docs,
                                        "top_n": len(docs)})
                resp.raise_for_status()
                d = resp.json()
                ranked = [short[x["index"]] for x in d["results"]]
                cost = (d.get("usage") or {}).get("cost")
                llm._log(processor="bench.skills.cohere", model="cohere/rerank-4-fast", purpose="rerank",
                         budget="backfill", privacy_class="cloud_allowed", cost_usd=cost, status="ok")
            else:
                convo = (f"[previous user message]\n{ctx.get('prev_user', '')[-400:]}\n[previous assistant message]\n"
                         f"{ctx.get('prev_assistant', '')[-500:]}\n[current user message]\n{c['query'][:1500]}")
                cand = "\n".join(f"- {card_text(n, desc.get(n, ''), True)}" for n in short)
                res = llm.chat([{"role": "user", "content": f"{convo}\n\n[candidate skills]\n{cand}\n\n{ASK}"}],
                               model=a.model, processor="bench.skills.shortlist_llm", privacy_class="cloud_allowed",
                               budget="backfill", timeout=60,
                               **({"reasoning": {"effort": "low"}} if "luna" in a.model or "gpt" in a.model else {}))
                m = re.search(r"\{.*\}", res["content"], re.S)
                picked = [n for n in json.loads(m.group(0)).get("skills", []) if n in short] if m else []
                ranked = picked + [n for n in short if n not in picked]  # chosen first, then the local order
                cost = res.get("cost_usd")
        except Exception as e:  # noqa: BLE001
            print("ERR", r["id"], str(e)[:150], file=sys.stderr)
            return None
        return {"id": r["id"], "corpus": a.corpus, "ranked": ranked, "picked": ranked[:5],
                "latency_ms": round(1000 * (time.perf_counter() - t0)), "cost_usd": cost}

    with ThreadPoolExecutor(a.workers) as ex, open(out, "a") as f:
        for res in ex.map(one, rows):
            if res:
                f.write(json.dumps(res) + "\n")
    got = [json.loads(line) for line in open(out)]
    lat = sorted(g["latency_ms"] for g in got)
    print(f"{len(got)} rows, p50 {lat[len(lat) // 2]} ms, cost {sum(g['cost_usd'] or 0 for g in got):.3f} USD",
          file=sys.stderr)


if __name__ == "__main__":
    main()
