#!/usr/bin/env python3
"""A8 collector: parse Hermes agent.log* 'API call #n' lines into system.agent_calls (idempotent on response id)."""
import glob, re, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory.db import connection
LINE = re.compile(r"^(\S+ \S+),\d+ INFO \[(\S+)\] agent\.conversation_loop: API call #(\d+): model=(\S+) provider=(\S+) "
                  r"in=(\d+) out=(\d+) total=\d+ latency=([\d.]+)s(?: cache=(\d+)/\d+ \(\d+%\))? id=(\S+)")
rows = []
for f in sorted(glob.glob("/root/.hermes/logs/agent.log*")):
    if f.endswith(".gz"):
        continue
    for line in open(f, errors="replace"):
        m = LINE.match(line)
        if m:
            at, sid, n, model, prov, i, o, lat, cache, rid = m.groups()
            rows.append((rid, datetime.strptime(at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc), sid, int(n), model, prov,
                         int(i), int(cache) if cache else None, int(o), float(lat), Path(f).name))
with connection() as conn:
    with conn.cursor() as cur:
        cur.executemany("""insert into system.agent_calls (response_id, at, session_id, call_no, model, provider, input_tokens,
                               cached_tokens, output_tokens, latency_s, source_log) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict do nothing""", rows)
print({"parsed": len(rows)})
