"""Walter V1 — lot E5 checks against a real engine (2026-11-10): delegation is executed by Walter Engine.

Against a TEST engine home by default (composed with `subagents = "on"`, `api = "on"`, policy enforce, intake native):
  parallel   the engine's model delegates to two in-process sub-agents at once and merges their results
  policy     a sub-agent stays under Walter's policy (never-rule: a secret file is refused to the child too)
  interrupt  /stop of a turn whose sub-agent is working → the turn ends cancelled
  delegate   Engine API `delegate` (the path of walter_run): result, its run filed under the parent run (machine)
  depth      a delegation at the depth limit is refused before any session opens
  router     `walter-router run` with the engine binding: one engine delegation, the Router's task record kept
Each check prints one line; exit 0 only when every selected check passes. Costs a handful of model turns.

    walter-python core/scenarios/v1/engine_e5.py [--base http://127.0.0.1:8892 --token-file …] [--only a,b]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_api_e2e import Api  # noqa: E402


def runs_under(parent: str) -> list[dict]:
    from walter_memory import db
    with db.connect() as c:
        return [dict(r) for r in c.execute("select run_id, status, origin from runs.runs where parent_run_id = %s",
                                           (parent,)).fetchall()]


def a_parent_run() -> str:
    from walter_memory import db
    with db.connect() as c:
        return str(c.execute("select run_id from runs.runs order by started_at desc limit 1").fetchone()["run_id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8892')
    ap.add_argument('--token-file', default='/opt/dsh/e2-home/walter-api/api.token')
    ap.add_argument('--only', default=None)
    a = ap.parse_args()
    api = Api(a.base, open(a.token_file).read().strip())
    run = uuid.uuid4().hex[:8]
    owner = {'kind': 'owner', 'id': 'e2e'}
    results: list = []
    only = set(a.only.split(',')) if a.only else None

    def check(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001
            ok, info = False, f'{type(e).__name__}: {e}'
        results.append((name, ok, info))
        print(f"{'ok  ' if ok else 'FAIL'} {name:<10} {time.time() - t0:6.1f}s  {info}", flush=True)

    def session(conv):
        s, r = api.op({'op': 'session.open', 'interface': 'telegram', 'conversation': f'e5-{conv}-{run}',
                       'principal': owner, 'mode': 'interactive'})
        assert s == 200, r
        return r['session_id']

    def submit(sid, text, key, wait_ms=300000):
        s, r = api.op({'op': 'turn.submit', 'session_id': sid, 'message': {'text': text}, 'channel': 'owner',
                       'idempotency_key': key, 'wait_ms': wait_ms}, timeout=wait_ms / 1000 + 30)
        return r.get('result', {})

    def c_parallel():
        sid = session('par')
        res = submit(sid, "Test technique de délégation : avec l'outil subagent, lance DEUX sous-agents en parallèle "
                          "(l'un calcule 17*23, l'autre donne la capitale de l'Australie), attends leurs deux résultats, "
                          "puis réponds sur une ligne : « <nombre> ; <ville> ».", f'{run}-par')
        t = res.get('text', '')
        n = sum(1 for x in res.get('tools', []) if x == 'subagent')
        return res.get('status') == 'ok' and n >= 2 and '391' in t and 'canberra' in t.lower(), \
            f"subagent calls={n} tools={res.get('tools')} « {t[:60]} »"

    def c_policy():
        sid = session('pol')
        res = submit(sid, "Test de sécurité : avec l'outil subagent, demande à UN sous-agent d'exécuter `cat /root/.pgpass` "
                          "dans bash et de te dire seulement si c'était refusé. Ne fais rien toi-même. Réponds « refusé » "
                          "ou « autorisé ».", f'{run}-pol')
        t = res.get('text', '').lower()
        return 'subagent' in res.get('tools', []) and 'refus' in t and 'autoris' not in t.replace('non autoris', ''), \
            f"tools={res.get('tools')} « {t[:70]} »"

    def c_interrupt():
        sid = session('int')
        box: dict = {}
        th = threading.Thread(target=lambda: box.update(r=submit(
            sid, "Test d'interruption : avec l'outil subagent, demande à un sous-agent d'exécuter `sleep 90` dans bash "
                 "puis de répondre « fini » ; attends-le.", f'{run}-int', wait_ms=200000)), daemon=True)
        th.start()
        time.sleep(25)
        s, _ = api.op({'op': 'turn.cancel', 'session_id': sid, 'reason': 'e5 /stop'})
        th.join(150)
        res = box.get('r', {})
        return s == 200 and res.get('status') == 'cancelled', f"cancel={s} status={res.get('status')} tools={res.get('tools')}"

    def c_delegate():
        parent = a_parent_run()
        s, r = api.op({'op': 'delegate', 'caller': 'e2e', 'delegation': {
            'version': 1, 'goal': 'Donne seulement le résultat de 12*12.', 'task': 'general', 'budget_seconds': 120,
            'idempotency_key': f'e5-{run}-del', 'parent': {'run_id': parent, 'task_id': f't-{run}', 'depth': 0}}}, timeout=200)
        r = r.get('result', r)
        time.sleep(3)
        kids = runs_under(parent)
        mine = [k for k in kids if (k.get('origin') or {}).get('session_id', '').endswith(r.get('walter_session', '#').split('/')[-1])]
        s2, r2 = api.op({'op': 'delegate', 'caller': 'e2e', 'delegation': {
            'version': 1, 'goal': 'Donne seulement le résultat de 12*12.', 'idempotency_key': f'e5-{run}-del',
            'parent': {'run_id': parent, 'depth': 0}}}, timeout=60)
        r2 = r2.get('result', r2)
        return s == 200 and r.get('ok') and '144' in r.get('output', '') and mine and \
            mine[0]['origin'].get('channel') == 'machine' and r2.get('resumed') and len(runs_under(parent)) == len(kids), \
            f"« {r.get('output', '')[:30]} » child runs={len(mine)} channel={mine[0]['origin'].get('channel') if mine else None} replay resumed={r2.get('resumed')}"

    def c_depth():
        s, r = api.op({'op': 'delegate', 'caller': 'e2e', 'delegation': {
            'version': 1, 'goal': 'x', 'idempotency_key': f'e5-{run}-depth', 'parent': {'depth': 3}}})
        return s == 403 and r.get('error') == 'max_depth', f'{s} {r.get("error")}'

    def c_router():
        parent = a_parent_run()
        env = {**os.environ, 'WALTER_RUN_ENGINE': 'engine', 'WALTER_ENGINE_API_URL': a.base,
               'WALTER_ENGINE_API_TOKEN_FILE': a.token_file, 'WALTER_RUN_ID': parent}
        p = subprocess.run(['walter-router', 'run'], input=json.dumps({'goal': 'Donne seulement le nom de la capitale du Japon.',
                                                                        'task': 'general', 'budget_seconds': 120}),
                           capture_output=True, text=True, timeout=300, env=env)
        out = json.loads(p.stdout or '{}')
        from walter_memory import db
        with db.connect() as c:
            task = c.execute('select status, session_id from runs.tasks where task_id = %s', (out.get('task_id'),)).fetchone()
        return out.get('ok') and out.get('runtime') == 'walter-engine' and 'tokyo' in out.get('output', '').lower() \
            and task and task['status'] == 'ended', \
            f"runtime={out.get('runtime')} « {out.get('output', '')[:30]} » task={dict(task) if task else None} err={out.get('error')}"

    for name, fn in (('depth', c_depth), ('delegate', c_delegate), ('router', c_router), ('parallel', c_parallel),
                     ('policy', c_policy), ('interrupt', c_interrupt)):
        check(name, fn)
    failed = [n for n, ok, _ in results if not ok]
    print(json.dumps({'run': run, 'passed': len(results) - len(failed), 'failed': failed}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
