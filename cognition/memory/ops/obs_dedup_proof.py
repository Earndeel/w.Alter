#!/usr/bin/env python3
"""Cleanup phase 2: proof, event by event, that the observability events copied into `core.events` have an exact
equivalent in `walter_logs` — one proof per (source, event type), never extrapolated from one type to another.

    obs_dedup_proof.py [--out report.json]

Read-only (one READ ONLY REPEATABLE READ transaction). Prints and writes counts only, never content.

How each core event is paired with walter_logs, and what "exact" means (every field of the core payload is either
equal to, or recomputable from, the walter_logs record; the connector's own functions are used for that):

  tool.called (hermes)      the state.db tool message it was built from (`output_ref` state.db:messages:<id>) is the
                            walter_logs `tool/result` with source_ref m<id> in the session of the same profile; its
                            call is the `tool/call` with the same call_id just before it. Checks: tool name, args
                            summary = summarise_args(call text), status, output size.
  tool.called (claude_code, codex, dsh)   `tool/result` and `tool/call` with the same session and call_id.
  skill.used (hermes)       the same tool message (source_id skill:<id>): tool = action, call args name = skill.
  conversation.started      walter_logs session (runtime, profile, native id = thread): start time, title, model,
                            parent, platform, cwd where the core payload has them.
  conversation.ended        walter_logs session: end time and the end fields kept in its meta.

Result per (source, type): total, exact, and every other event counted in one named class (absent, differs on
field X, differs only where walter_logs masked a secret, duplicate of another core event with the same payload).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'connectors')]

from psycopg.rows import tuple_row  # noqa: E402
from walter_memory.db import connect  # noqa: E402
import hermes as hermes_conn  # noqa: E402
import agent_sessions as agent_conn  # noqa: E402

MASKED = re.compile(r'«secret[^»]*»')


def hermes_status(text):
    return hermes_conn.tool_status(text)


def run(cur) -> dict:
    report = {}

    def tally(key, cls):
        report.setdefault(key, collections.Counter())[cls] += 1

    # ---- tool.called + skill.used, Hermes: pair by state.db message id ---------------------------------------------
    cur.execute("""
        with c as (
          select e.event_id, e.event_type, e.source_id, e.thread_id sid, coalesce(e.payload->>'profile', 'main') prof,
                 e.payload, coalesce(substring(e.payload->>'output_ref' from 'state.db:messages:(\\d+)$'),
                                     substring(e.source_id from 'skill:(\\d+)$')) mid
          from core.events e where e.source = 'hermes' and e.event_type in ('tool.called', 'skill.used'))
        select c.event_type, c.payload, c.mid, r.seq is not null, r.tool, r.status, r.chars, r.text,
               k.seq is not null, k.tool, k.text
        from c
        left join walter_logs.sessions s on s.runtime = 'hermes' and s.native_id = c.sid
             and coalesce(s.profile, 'main') = c.prof
        left join walter_logs.events r on r.session_id = s.session_id and r.source_ref = 'm' || c.mid
             and r.type = 'tool/result'
        left join lateral (select seq, tool, text from walter_logs.events k where k.session_id = s.session_id
             and k.type = 'tool/call' and k.call_id = r.call_id and k.seq < r.seq order by k.seq desc limit 1) k
             on true""")
    seen = collections.Counter()
    for etype, p, mid, has_r, r_tool, r_status, r_chars, r_text, has_k, k_tool, k_text in cur:
        key = f'hermes {etype}'
        if mid is None:
            tally(key, 'no state.db reference in core payload')
            continue
        if not has_r:
            tally(key, 'absent from walter_logs')
            continue
        dup_key = (etype, json.dumps(p, sort_keys=True))
        seen[dup_key] += 1
        if etype == 'skill.used':
            try:
                name = (json.loads(k_text or '') or {}).get('name') if has_k else None
            except ValueError:
                name = None
            tool = k_tool if has_k else r_tool
            if tool == p.get('action') and name == p.get('skill'):
                tally(key, 'exact')
            elif not has_k:
                tally(key, 'call missing in walter_logs (result present)')
            else:
                tally(key, 'differs: ' + ', '.join(x for x, ok in (('action', tool == p.get('action')),
                                                                   ('skill', name == p.get('skill'))) if not ok))
            continue
        diffs = []
        tool = k_tool if has_k and k_tool not in (None, 'tool_call') else r_tool
        if tool != p.get('tool'):
            diffs.append('tool name' + (' (walter_logs has generic "tool_call")' if tool in (None, 'tool_call')
                                        else ''))
        want_args = p.get('args_summary')
        got_args = hermes_conn.summarise_args(k_text) if has_k else None
        masked = False
        if got_args != want_args:
            if has_k and MASKED.search(k_text or ''):
                masked = True
            else:
                diffs.append('args' if has_k else 'args (no call in walter_logs)')
        if (p.get('output_chars') or 0) != (r_chars or 0) and not MASKED.search(r_text or ''):
            diffs.append('output size')
        if p.get('status') != hermes_status(r_text) and not MASKED.search(r_text or ''):
            diffs.append('status')
        if not diffs:
            tally(key, 'exact' + (' except secrets masked in walter_logs' if masked else ''))
        else:
            tally(key, 'differs: ' + ', '.join(diffs))
    report['hermes tool.called duplicates in core (same payload)'] = collections.Counter(
        {'events beyond the first': sum(n - 1 for (t, _), n in seen.items() if t == 'tool.called' and n > 1)})

    # ---- tool.called, Claude Code / Codex / DSH: pair by session + call_id -------------------------------------------
    cur.execute("""
        select e.source, e.payload, r.seq is not null, r.tool, r.status, r.chars, k.seq is not null, k.tool, k.text,
               (select count(*) from walter_logs.events x where x.session_id = s.session_id and x.type = 'tool/result'
                  and x.call_id = e.payload->>'call_id')
        from core.events e
        left join walter_logs.sessions s on s.runtime = e.source and s.native_id = e.payload->>'session_id'
        left join lateral (select seq, tool, status, chars, call_id from walter_logs.events r
             where r.session_id = s.session_id and r.type = 'tool/result' and r.call_id = e.payload->>'call_id'
             order by seq limit 1) r on true
        left join lateral (select seq, tool, text from walter_logs.events k where k.session_id = s.session_id
             and k.type = 'tool/call' and k.call_id = e.payload->>'call_id' order by seq limit 1) k on true
        where e.event_type = 'tool.called' and e.source in ('claude_code', 'codex', 'dsh')""")
    for src, p, has_r, r_tool, r_status, r_chars, has_k, k_tool, k_text, n_res in cur:
        key = f'{src} tool.called'
        if not has_r and not has_k:
            tally(key, 'absent from walter_logs')
            continue
        diffs, masked = [], False
        tool = k_tool if has_k else r_tool
        if (tool or 'unknown') != p.get('tool'):
            diffs.append('tool name')
        got_args = agent_conn.summarise_args(k_text) if has_k else None
        if got_args != p.get('args_summary'):
            if has_k and MASKED.search(k_text or ''):
                masked = True
            else:
                diffs.append('args')
        if not has_r:
            diffs.append('result missing')
        else:
            if (p.get('output_chars') or 0) != (r_chars or 0):
                diffs.append('output size')
            if (p.get('status') or 'ok') != (r_status or 'ok'):
                diffs.append('status')
        if n_res > 1:
            diffs.append('several results for the call id')
        tally(key, 'exact' + (' except secrets masked in walter_logs' if masked else '') if not diffs
              else 'differs: ' + ', '.join(diffs))

    # ---- conversation.started / ended: pair with the walter_logs session ------------------------------------------
    cur.execute("""
        select e.source, e.event_type, e.occurred_at, e.payload, s.session_id is not null, s.started_at, s.ended_at,
               s.title, s.model, s.parent_session_id, s.platform, s.cwd, s.meta
        from core.events e
        left join walter_logs.sessions s on s.runtime = e.source and s.native_id = e.thread_id
             and (e.source <> 'hermes' or coalesce(s.profile, 'main') = coalesce(e.payload->>'profile', 'main'))
        where e.event_type in ('conversation.started', 'conversation.ended')""")
    for src, etype, at, p, has_s, s_start, s_end, title, model, parent, platform, cwd, meta in cur:
        key = f'{src} {etype}'
        if not has_s:
            tally(key, 'absent from walter_logs')
            continue
        meta = meta or {}
        diffs = []

        def same_time(a, b):
            return a is not None and b is not None and abs((a - b).total_seconds()) <= 1

        if etype == 'conversation.started':
            if not same_time(at, s_start):
                diffs.append('start time')
            checks = {'title': title, 'model': model, 'parent_session_id': parent, 'platform': platform, 'cwd': cwd}
            for f, v in checks.items():
                if f in p and (p.get(f) or None) != (v or None):
                    diffs.append(f)
            for f in ('cli_version', 'originator', 'delegation_depth'):
                if p.get(f) is not None and f not in meta:
                    diffs.append(f'{f} not kept in walter_logs')
        else:
            if not same_time(at, s_end):
                diffs.append('end time')
            for f, mf in (('end_reason', 'end_reason'), ('message_count', 'message_count'),
                          ('tool_call_count', 'tool_call_count')):
                if p.get(f) is not None and p.get(f) != meta.get(mf):
                    diffs.append(f)
            if p.get('cost_usd') is not None and meta.get('estimated_cost_usd') is None:
                diffs.append('cost not kept in walter_logs')
            elif p.get('cost_usd') is not None and abs(float(p['cost_usd']) - float(meta['estimated_cost_usd'])) > 1e-9:
                diffs.append('cost (core = actual cost when known)')
        tally(key, 'exact' if not diffs else 'differs: ' + ', '.join(sorted(set(diffs))))
    return {k: dict(v.most_common()) for k, v in report.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    with connect() as conn:
        conn.execute('set transaction isolation level repeatable read, read only')
        cur = conn.cursor(row_factory=tuple_row)
        cur.execute("select now(), pg_current_snapshot()::text")
        at, snap = cur.fetchone()
        res = run(conn.cursor(name='proof_rows', row_factory=tuple_row))
    out = {'at': at.isoformat(), 'txid_snapshot': snap, 'tool': 'walter/memory/ops/obs_dedup_proof.py',
           'results': res,
           'totals': {k: {'total': sum(v.values()), 'exact': sum(n for c, n in v.items() if c.startswith('exact'))}
                      for k, v in res.items() if 'duplicates' not in k}}
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    print(text)
    if a.out:
        Path(a.out).write_text(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
