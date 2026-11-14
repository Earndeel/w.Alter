"""P3 exit criterion: unified search vs Hindsight recall on the 30 real questions (LLM judge, top-5)."""
import concurrent.futures as cf, json, sys, time
import httpx
sys.path.insert(0, "/walter/cognition/memory")
from walter_memory import llm, search
Q = json.load(open("/opt/walter-voice-memory/bench/queries.json"))
EXCL = [{"not": {"tags": ["quarantine:noise"], "match": "any_strict"}}]
def hindsight(q):
    t = time.perf_counter()
    r = httpx.post("http://127.0.0.1:8888/v1/default/banks/walter/memories/recall",
                   json={"query": q, "budget": "mid", "max_tokens": 1500, "tag_groups": EXCL}, timeout=60).json()
    return [x["text"] for x in r["results"][:5]], (time.perf_counter() - t) * 1000
def unified(q, rerank):
    t = time.perf_counter()
    r = search.search(q, limit=5, rerank=rerank, max_privacy="redacted_cloud")
    return [f"[{x['source']}/{x['label']} {str(x['occurred_at'])[:10]}] {x['text'][:400]}" for x in r], (time.perf_counter() - t) * 1000
def judge(q, mems):
    prompt = (f"Question de l'utilisateur : {q}\nÉléments retrouvés :\n" + "\n".join(f"{i+1}. {m[:450]}" for i, m in enumerate(mems))
              + '\n\nRéponds en JSON {"answerable": true|false, "useful": <nombre d\'éléments utiles pour répondre, 0-5>}.')
    for _ in range(3):
        try:
            c = llm.chat([{"role": "user", "content": prompt}], model="google/gemini-3.6-flash", processor="bench.p3",
                         privacy_class="redacted_cloud", budget="backfill", response_format={"type": "json_object"},
                         reasoning={"effort": "low"}, max_tokens=4000)["content"]
            return json.loads(c[c.find("{"):c.rfind("}") + 1])
        except Exception:
            pass
    return {"answerable": False, "useful": 0}
def run(q):
    out = {}
    for name, f in (("hindsight", lambda: hindsight(q)), ("unified", lambda: unified(q, False)), ("unified+rerank", lambda: unified(q, True))):
        mems, ms = f(); out[name] = {**judge(q, mems), "ms": ms}
    return q, out
if __name__ == "__main__":
  with cf.ThreadPoolExecutor(5) as ex: res = list(ex.map(run, Q))
  for name in ("hindsight", "unified", "unified+rerank"):
    ms = sorted(r[1][name]["ms"] for r in res)
    print(f"{name:15} répondables {sum(r[1][name]['answerable'] for r in res)}/30  utiles {sum(r[1][name]['useful'] for r in res)}/150  p50 {ms[15]:.0f} ms")
  json.dump(res, open("/walter/cognition/memory/bench/search_vs_hindsight.json", "w"), ensure_ascii=False, indent=1, default=str)
  for q, o in res:
    if o["hindsight"]["answerable"] != o["unified+rerank"]["answerable"]:
        print("  diff:", q, "H", o["hindsight"]["answerable"], "U+R", o["unified+rerank"]["answerable"])
