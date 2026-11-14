"""Walter V1 — the engine with its modules, on the live instance (2026-11-10).

One owner conversation through the Engine API (door telegram, test principal `e2e`), then the trace it leaves:
  memory     a question only Walter Memory can answer (context injected and/or memory tools)
  browse     a web search through Walter Browse
  router     Walter Router asked which model fits a task + a Walter skill looked up
  trace      the conversation's runs (Run Plane), bus events and model costs, by aggregates
Prints one line per check; exit 0 when all pass. Costs a few model turns.

    walter-python core/scenarios/v1/walter_v1_live.py [--base http://127.0.0.1:8895 --token-file @instance/bootstrap/engine/api.token]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_api_e2e import Api  # noqa: E402


def token_file(arg: str | None) -> str:
    if arg:
        return arg
    root = subprocess.run(['walter', 'instance', 'path'], capture_output=True, text=True).stdout.strip()
    return f'{root}/bootstrap/engine/api.token'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8895')
    ap.add_argument('--token-file', default=None)
    ap.add_argument('--only', default=None)
    a = ap.parse_args()
    api = Api(a.base, open(token_file(a.token_file)).read().strip())
    run = uuid.uuid4().hex[:8]
    owner = {'kind': 'owner', 'id': 'e2e'}
    s, r = api.op({'op': 'session.open', 'interface': 'telegram', 'conversation': f'v1live-{run}', 'principal': owner})
    sid, walter_session = r['session_id'], r['walter_session']
    results: list = []
    only = set(a.only.split(',')) if a.only else None

    def submit(text, key):
        s, r = api.op({'op': 'turn.submit', 'session_id': sid, 'message': {'text': text}, 'channel': 'owner',
                       'idempotency_key': f'{run}-{key}', 'wait_ms': 300000}, timeout=330)
        return r.get('result', {})

    def check(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001
            ok, info = False, f'{type(e).__name__}: {e}'
        results.append((name, ok, info))
        print(f"{'ok  ' if ok else 'FAIL'} {name:<8} {time.time() - t0:6.1f}s  {info}", flush=True)

    def c_memory():
        res = submit("Que sais-tu de Sagora, l'application de streaming de ma famille ? Deux phrases, avec la date de "
                     "ce que tu sais le plus récemment.", 'mem')
        t = res.get('text', '').lower()
        mem_tools = [x for x in res.get('tools', []) if 'memory' in x or 'person' in x]
        return res.get('status') == 'ok' and ('stremio' in t or 'stream' in t) and len(t) > 40, \
            f"memory tools={mem_tools} « {res.get('text', '')[:70]} »"

    def c_browse():
        res = submit('Cherche sur le web la dernière version LTS de Node.js publiée et donne seulement son numéro et sa '
                     'source.', 'web')
        tools = res.get('tools', [])
        return res.get('status') == 'ok' and any('browse' in x or 'web' in x for x in tools), \
            f"tools={tools} « {res.get('text', '')[:70]} »"

    def c_router():
        res = submit("Deux vérifications d'outillage : 1) demande à Walter Router (walter_route) quel modèle il choisirait "
                     "pour générer une image ; 2) cherche dans les skills Walter (skills_search) la procédure pour "
                     "déployer Sagora. Réponds en deux lignes.", 'route')
        tools = res.get('tools', [])
        # the engine reaches non-core Walter tools through its `walter_call` meta-tool (MCP toolset `core`)
        return res.get('status') == 'ok' and any('walter_route' in x or 'walter_call' in x for x in tools) \
            and any('skill' in x for x in tools) and 'image' in res.get('text', '').lower(), \
            f"tools={tools} « {res.get('text', '')[:80]} »"

    def c_trace():
        time.sleep(3)
        from walter_memory import db
        with db.connect() as c:
            runs = c.execute("""select status, count(*) n from runs.runs where origin->>'session_id' = %s group by 1""",
                             (walter_session,)).fetchall()
            ids = [str(x['run_id']) for x in c.execute("select run_id from runs.runs where origin->>'session_id' = %s",
                                                        (walter_session,)).fetchall()]
            # subscriptions (Codex, Claude) have no per-call price: their cost is the tokens, recorded per call
            cost = c.execute("""select count(*) calls, round(sum(coalesce(cost_usd, 0))::numeric, 4) usd,
                                       count(*) filter (where usage is not null) metered,
                                       sum(coalesce((usage->>'in')::bigint, 0) + coalesce((usage->>'out')::bigint, 0)) tokens
                                from models.exec_log where run_id = any(%s::uuid[])""", (ids,)).fetchone()
            bus = c.execute("""select type, count(*) n from bus.events where subject = any(%s) or payload->>'run_id' = any(%s)
                               group by 1 order by 1""", (ids, ids)).fetchall()
        st = {x['status']: x['n'] for x in runs}
        types = {x['type']: x['n'] for x in bus}
        n = sum(st.values())
        return n >= 1 and st.get('ended', 0) == n and cost['calls'] >= n and cost['metered'] == cost['calls'] \
            and 'run.created' in types and types.get('run.ended') == n, \
            f"runs={st} calls={cost['calls']} metered={cost['metered']} tokens={cost['tokens']} usd={cost['usd']} bus={types}"

    for name, fn in (('memory', c_memory), ('browse', c_browse), ('router', c_router), ('trace', c_trace)):
        check(name, fn)
    failed = [n for n, ok, _ in results if not ok]
    print(json.dumps({'session_id': sid, 'walter_session': walter_session, 'passed': len(results) - len(failed), 'failed': failed}))
    return 1 if failed else 0


if __name__ == '__main__':
    rc = main()
    import sys                                             # the objectives this scenario opened are test data
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from e2e_objectives import close
    close('objectif de test du scénario walter_v1_live')
    raise SystemExit(rc)
