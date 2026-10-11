#!/usr/bin/env python3
"""A8 collector: parse Hermes agent.log* 'API call #n' lines into system.agent_calls (idempotent on response id).

When walter-context is the active context engine it logs one `walter-context: {json}` trace per request, just before
the call; the call that follows in the same session gets it (context_engine='walter-context', context_trace=json).
"""
import glob, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory.db import connection
LINE = re.compile(r"^(\S+ \S+),\d+ INFO \[(\S+)\] agent\.conversation_loop: API call #(\d+): model=(\S+) provider=(\S+) "
                  r"in=(\d+) out=(\d+) total=\d+ latency=([\d.]+)s(?: cache=(\d+)/\d+ \(\d+%\))? id=(\S+)")
TRACE = re.compile(r"^\S+ \S+,\d+ INFO (?:\[(\S+)\] )?agent\.walter_context: walter-context: (\{.*\})\s*$")
rows = []
for f in sorted(glob.glob("/root/.hermes/logs/agent.log*")):
    if f.endswith(".gz"):
        continue
    pending = {}                                    # session → latest walter-context trace not yet attached
    for line in open(f, errors="replace"):
        t = TRACE.match(line)
        if t:
            try:
                tr = json.loads(t.group(2))
                pending[t.group(1) or tr.get("session") or "-"] = tr
            except ValueError:
                pass
            continue
        m = LINE.match(line)
        if m:
            at, sid, n, model, prov, i, o, lat, cache, rid = m.groups()
            tr = pending.pop(sid, None)
            rows.append((rid, datetime.strptime(at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc), sid, int(n), model, prov,
                         int(i), int(cache) if cache else None, int(o), float(lat), Path(f).name,
                         "walter-context" if tr else "baseline", json.dumps(tr) if tr else None))
with connection() as conn:
    with conn.cursor() as cur:
        cur.executemany("""insert into system.agent_calls (response_id, at, session_id, call_no, model, provider, input_tokens,
                               cached_tokens, output_tokens, latency_s, source_log, context_engine, context_trace)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict do nothing""", rows)
print({"parsed": len(rows), "walter_context": sum(1 for r in rows if r[11] == "walter-context")})
