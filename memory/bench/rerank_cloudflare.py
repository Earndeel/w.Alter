"""Rerankers without OpenRouter credit (2026-10-05): which one improves Walter Memory's unified search?

Variants on the same 20 cloud_allowed candidates per question (30 real questions, /opt/walter-voice-memory/bench):
  rrf        fused order, no rerank (today's fallback while OpenRouter is at 0)
  cf-base    Cloudflare Workers AI @cf/baai/bge-reranker-base (the only reranker in the Workers AI catalogue)
  local-m3   BAAI/bge-reranker-v2-m3 on the VM CPU (multilingual), computed by step `local`
Judge: an LLM through walter-llm (task "general"), "useful elements in top 5" as in the P3 bench.

  python bench/rerank_cloudflare.py candidates     (walter-memory venv: search + Cloudflare)
  python bench/rerank_cloudflare.py local          (a venv with sentence-transformers)
  python bench/rerank_cloudflare.py judge          (walter-memory venv)
"""
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "rerank_cloudflare.json"
Q = json.load(open("/opt/walter-voice-memory/bench/queries.json"))


def env(name):
    for line in open("/root/.hermes/.env"):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"')


def candidates():
    import httpx
    sys.path.insert(0, "/opt/walter-memory")
    from walter_memory import search
    acct, tok = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_AI_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/baai/bge-reranker-base"
    data = {}
    for q in Q:
        res = search.search(q, limit=20, rerank=False, max_privacy="cloud_allowed")
        docs = [r["text"][:1200] for r in res]
        t = time.perf_counter()
        r = httpx.post(url, headers={"Authorization": f"Bearer {tok}"}, timeout=30,
                       json={"query": q, "contexts": [{"text": d} for d in docs], "top_k": len(docs)})
        ms = (time.perf_counter() - t) * 1000
        ranked = r.json()["result"]["response"]
        data[q] = {"docs": docs, "rrf": list(range(len(docs))), "cf-base": [x["id"] for x in ranked], "cf_ms": ms}
        print(f"{ms:6.0f} ms  {q}", flush=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def local():
    import numpy as np
    import torch
    from sentence_transformers import CrossEncoder
    torch.set_num_threads(4)
    ce = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu", max_length=256)
    ce.predict([("warmup", "warmup")])
    data = json.loads(OUT.read_text())
    for q, d in data.items():
        t = time.perf_counter()
        s = ce.predict([(q, x) for x in d["docs"]], batch_size=20)
        d["local_ms"] = (time.perf_counter() - t) * 1000
        d["local-m3"] = [int(i) for i in np.argsort(-np.asarray(s))]
        print(f"{d['local_ms']:6.0f} ms  {q}", flush=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def judge():
    import httpx
    tok = re.search(r"WALTER_LLM_TOKEN: (\S+)", (HERE / ".wllm-bench.yaml").read_text()).group(1)
    data = json.loads(OUT.read_text())
    variants = [v for v in ("rrf", "cf-base", "local-m3") if v in next(iter(data.values()))]
    tot = {v: [0, 0] for v in variants}
    for q, d in data.items():
        for v in variants:
            top = [d["docs"][i] for i in d[v][:5]]
            prompt = (f"Question de l'utilisateur : {q}\nÉléments retrouvés :\n" + "\n".join(f"{i+1}. {m[:450]}" for i, m in enumerate(top))
                      + '\n\nRéponds uniquement en JSON {"answerable": true|false, "useful": <nombre d\'éléments utiles pour répondre, 0-5>}.')
            for _ in range(3):
                try:
                    r = httpx.post("http://127.0.0.1:8894/v1/chat/completions", headers={"Authorization": f"Bearer {tok}"},
                                   timeout=180, json={"model": "general", "max_tokens": 2000,
                                                      "messages": [{"role": "user", "content": prompt}]})
                    c = r.json()["choices"][0]["message"]["content"]
                    j = json.loads(c[c.find("{"):c.rfind("}") + 1])
                    break
                except Exception:
                    j = {"answerable": False, "useful": 0}
            d.setdefault("judge", {})[v] = j
            tot[v][0] += bool(j.get("answerable")); tot[v][1] += int(j.get("useful") or 0)
        print(q, {v: d["judge"][v] for v in variants}, flush=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    for v in variants:
        lat = [d.get({"cf-base": "cf_ms", "local-m3": "local_ms"}.get(v, ""), 0) for d in data.values()]
        print(f"{v:9s} answerable {tot[v][0]}/{len(data)}  useful {tot[v][1]}/{5 * len(data)}  latency {sum(lat) / len(lat):.0f} ms")


if __name__ == "__main__":
    {"candidates": candidates, "local": local, "judge": judge}[sys.argv[1]]()
