"""Cold-start probe: one judgement call per target after a long idle gap. Usage: GAP OUT.jsonl [liquid-first|or-first]"""
import json, sys, time
import liquid_common as lc
gap = int(sys.argv[1]); out = sys.argv[2]
order = sys.argv[3] if len(sys.argv) > 3 else "liquid-first"
Q = {"q": {"type": "noul", "instructions": "Est-ce une salutation ?"}}
seq = [("liquid", "d1.2"), ("openrouter", "d1.2"), ("liquid", "d1.2-ultra"), ("openrouter", "d1.2-ultra")]
if order != "liquid-first":
    seq = [seq[1], seq[0], seq[3], seq[2]]
time.sleep(gap)
with open(out, "w") as f:
    for prov, model in seq:
        r = lc.liquid(model, {"state": "bonjour", "questions": Q}) if prov == "liquid" else lc.or_decide(model, {"state": "bonjour", "questions": Q})
        row = {"phase": "I", "provider": prov, "model": model, "mode": f"idle{gap}s-{order}", "status": r["status"], "ms": r["ms"], "at": time.strftime("%H:%M:%S")}
        f.write(json.dumps(row) + "\n"); print(row, flush=True)
