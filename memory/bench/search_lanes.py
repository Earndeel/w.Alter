import concurrent.futures as cf, json, sys
sys.path.insert(0, "/opt/walter-memory"); sys.path.insert(0, "/opt/walter-memory/bench")
from search_vs_hindsight import judge, Q
from walter_memory import search
def fmt(r): return [f"[{x['source']}/{x['label']} {str(x['occurred_at'])[:10]}] {x['text'][:400]}" for x in r]
def run(q):
    r = search.search(q, limit=5, max_privacy="redacted_cloud", rerank=True)
    return judge(q, fmt(r)), r[0]["latency_ms"] if r else 0
with cf.ThreadPoolExecutor(5) as ex: res = list(ex.map(run, Q))
ms = sorted(x[1] for x in res)
print(f"lanes+rerank répondables {sum(x[0]['answerable'] for x in res)}/30  utiles {sum(x[0]['useful'] for x in res)}/150  p50 {ms[15]} ms")
