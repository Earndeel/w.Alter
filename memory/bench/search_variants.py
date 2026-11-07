import concurrent.futures as cf, json, sys
sys.path.insert(0, "/opt/walter-memory"); sys.path.insert(0, "/opt/walter-memory/bench")
from search_vs_hindsight import judge, Q
from walter_memory import search
def fmt(r): return [f"[{x['source']}/{x['label']} {str(x['occurred_at'])[:10]}] {x['text'][:400]}" for x in r]
V = {"derived+rerank": dict(sources=["hindsight", "user_model_compiler"], rerank=True),
     "events+rerank": dict(include_derived=False, rerank=True),
     "derived-norerank": dict(sources=["hindsight", "user_model_compiler"], rerank=False)}
def run(q): return {v: judge(q, fmt(search.search(q, limit=5, max_privacy="redacted_cloud", **kw))) for v, kw in V.items()}
with cf.ThreadPoolExecutor(5) as ex: res = list(ex.map(run, Q))
for v in V: print(f"{v:18} répondables {sum(r[v]['answerable'] for r in res)}/30  utiles {sum(r[v]['useful'] for r in res)}/150")
