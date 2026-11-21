"""Controlled load on the live preflight: N requests at once (anonymous test messages, test sessions, no run), the way
three sub-agent turns arrive together. Prints aggregates only (times, level, late sources)."""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
MSG = ["Que sait-on des décisions d'architecture récentes de Walter Memory et de leur raison ?",
       "Fais le point sur le projet Walter Router : où en est-on et que reste-t-il à décider ?",
       "Retrouve ce qui a été décidé sur les sauvegardes restic et dis-moi ce qui a changé depuis.",
       "Rappelle-moi les règles en vigueur sur les secrets et les clés d'API, avec leurs dates.",
       "Quelles décisions ont été prises sur le moteur unique et l'arrêt de Hermes ?",
       "Résume l'état du module walter-skills et ses dernières évolutions."]
def one(i):
    body = {"turn_id": f"load:{time.time_ns()}:{i}", "message": MSG[i % len(MSG)], "runtime": "dsh",
            "session_id": f"dsh/vm/e2e-load-{int(time.time())}-{i}", "privacy_class": "cloud_allowed",
            "exclude_blocks": ["capabilities"], "answer_within_ms": 7000}
    t0 = time.monotonic()
    r = urllib.request.Request("http://127.0.0.1:8897/preflight?inject=1", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=7) as resp:
            out = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ms": round((time.monotonic() - t0) * 1000), "error": type(e).__name__}
    p = out.get("pack") or {}
    plan = out.get("plan") or {}
    return {"i": i, "ms": round((time.monotonic() - t0) * 1000), "level": plan.get("level"),
            "degraded": bool((plan.get("decision") or {}).get("degraded")), "retrieval_ms": p.get("retrieval_ms"),
            "late": p.get("late"), "tokens": p.get("tokens_per_message"),
            "blocks": {b["id"]: round(b.get("ms") or 0) for b in p.get("blocks") or []}}
with ThreadPoolExecutor(N) as ex:
    rows = list(ex.map(one, range(N)))
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
ms = sorted(r["ms"] for r in rows)
print(json.dumps({"n": N, "max_ms": ms[-1], "median_ms": ms[len(ms) // 2], "timeouts": sum("error" in r for r in rows),
                  "late": sum(bool(r.get("late")) for r in rows), "degraded": sum(bool(r.get("degraded")) for r in rows)}))
