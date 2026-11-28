"""Walter Engine native — end-to-end checks of what DSH used to run (mission « Walter Native Engine », 2026-11-17).

Runs against a native engine (`walter-python -m walter_engine serve`, by default a side-by-side trial on 18895) with
the scenarios' test account `e2e` (identity: a test principal on every door, judged under the `test` preset, so every
shell / Python / delegation call ASKS: an approver thread answers `allow_once` as the session's own account — the approval
path is exercised on every call). Synthetic content only. Each check prints one line; exit 0 only when all pass.

  python_persist   a variable set in one turn is there in the next (one kernel per conversation)
  python_tools     discovery (`tools.search`) + `asyncio.gather` of two real tools from the kernel, journaled as nested calls
  subagent         a foreground sub-agent answers; its session names its parent
  background       a background sub-agent settles and wakes the conversation (a new turn, notice subagent-settled)
  bash_job         `bash(background=True)` → engine job → wake when it ends
  restart          graceful restart during a tool call: the call is stopped and journaled, the turn is closed
                   `interrupted`, and the Python kernel's variables come back (snapshot)
  crash            SIGKILL during a tool call: at the next start the call gets « résultat inconnu », the turn is
                   closed `interrupted`, and the command's side effect is not run a second time

    walter-python core/scenarios/v1/engine_native.py --base http://127.0.0.1:18895 \\
        --token-file @instance/bootstrap/engine/api.token --state <engine state dir> [--restart-unit walter-engine-trial]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


class Api:
    def __init__(self, base: str, token: str):
        self.base, self.token = base.rstrip('/'), token

    def op(self, body: dict, timeout: float = 300) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + '/v1', data=json.dumps({'version': 1, **body}).encode(),
                                     headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.load(e)
            except ValueError:                      # a proxy / restart page, not the API
                return e.code, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:18895')
    ap.add_argument('--token-file', required=True)
    ap.add_argument('--state', required=True, help='the engine state directory (sessions/ is read to check the journal)')
    ap.add_argument('--restart-unit', default=None)
    ap.add_argument('--only', default=None)
    a = ap.parse_args()
    tf = a.token_file
    if tf.startswith("@instance/"):        # the instance (pointer /etc/walter/instance), never a fixed path
        tf = str(Path(open("/etc/walter/instance").read().strip()) / tf.removeprefix("@instance/"))
    api = Api(a.base, open(tf).read().strip())
    run = uuid.uuid4().hex[:8]
    principal = {'kind': 'owner', 'id': 'e2e'}
    sid = f'telegram/e2e/native-{run}'
    only = set(a.only.split(',')) if a.only else None
    results: list[tuple[str, bool, str]] = []
    stop = threading.Event()
    answered: list[str] = []

    def approver():
        while not stop.is_set():
            try:
                s, r = api.op({'op': 'approval.list', 'session_id': sid}, timeout=10)
                for p in r.get('approvals') or []:
                    s2, r2 = api.op({'op': 'approval.answer', 'request_id': p['request_id'], 'decision': 'allow_once',
                                     'principal': principal}, timeout=10)
                    if s2 != 200:                   # never hang silently on a refused answer
                        print(f"approver: answer refused {s2} {r2}", flush=True)
                    answered.append(p.get('tool') or '?')
            except Exception:  # noqa: BLE001 — the engine may be restarting
                pass
            stop.wait(0.5)

    threading.Thread(target=approver, daemon=True).start()
    s, opened = api.op({'op': 'session.open', 'interface': 'telegram', 'conversation': f'native-{run}',
                        'principal': principal, 'mode': 'interactive'})
    kernel = (opened.get('walter_session') or '').split('/')[-1]
    journal = Path(a.state) / 'sessions' / f'{kernel}.jsonl'

    def events() -> list[dict]:
        out = []
        for line in journal.read_text().splitlines()[1:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    def submit(text, key, wait_ms=240000):
        s, r = api.op({'op': 'turn.submit', 'session_id': sid, 'message': {'text': text}, 'channel': 'owner',
                       'idempotency_key': f'{run}-{key}', 'wait_ms': wait_ms})
        return r.get('result', {})

    def wait_turns(n: int, timeout: float = 240) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            evs = events()
            if sum(1 for e in evs if e['type'] == 'turn/end') >= n:
                return True
            time.sleep(1)
        return False

    def wait_woken(n0: int, kind: str, token: str, timeout: float = 240) -> tuple[bool, list, str]:
        """The wake notice (`kind`), then an answer carrying `token` after it, then the turn closed. A notice that
        arrives while the turn is still running is spliced into it (DSH did the same: agent/inbox/spliced) — the
        wake is then a later step of the same turn, not a new turn; both are a wake."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            evs = events()[n0:]
            idx = [i for i, e in enumerate(evs) if e['type'] == 'user/message'
                   and (e['data'].get('source') or {}).get('kind') == kind]
            if idx:
                after = evs[idx[0] + 1:]
                said = [e['data'].get('text') or '' for e in after if e['type'] == 'assistant/message']
                if any(token in t for t in said) and any(e['type'] == 'turn/end' for e in after):
                    return True, idx, said[-1]
            time.sleep(1)
        evs = events()[n0:]
        last = next((e['data'].get('text') for e in reversed(evs) if e['type'] == 'assistant/message' and e['data'].get('text')), '')
        return False, [], last or ''

    def check(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            ok, info = fn()
        except Exception as e:  # noqa: BLE001
            ok, info = False, f'{type(e).__name__}: {e}'
        results.append((name, ok, info))
        print(f"{'ok  ' if ok else 'FAIL'} {name:<15} {time.time() - t0:6.1f}s  {info}", flush=True)

    def c_python_persist():
        r1 = submit('Test technique : avec ton outil python, exécute exactement `x = 41` puis réponds « fait ».', 'p1')
        r2 = submit('Avec ton outil python, évalue `x + 1` et réponds seulement le résultat.', 'p2')
        return '42' in r2.get('text', '') and 'python' in r2.get('tools', []), \
            f"{r1.get('status')}/{r2.get('status')} « {r2.get('text', '')[:40]} » tools={r2.get('tools')}"

    def c_python_tools():
        r = submit('Test technique : dans UN SEUL appel à ton outil python, exécute '
                   '`found = await tools.search("fichiers"); a, b = await asyncio.gather('
                   'tools.read(file_path="/etc/hostname"), tools.glob(pattern="*.md", path="/walter/core/engine")); '
                   'print(len(found) > 0, len(str(a)) > 0, len(str(b)) > 0)` et réponds seulement ce qui a été affiché.',
                   'p3')
        nested = [e['data'].get('name') for e in events() if e['type'] == 'tool/call' and e['data'].get('nested')]
        ok = {'read', 'glob'} <= set(nested) and 'True True True' in r.get('text', '')
        return ok, f"nested={nested[:4]} « {r.get('text', '')[:40]} »"

    def c_subagent():
        r = submit(f'Test technique : délègue à un sous-agent (outil subagent, premier plan) cette mission exacte : '
                   f'« Réponds seulement pong-{run} ». Puis rapporte seulement sa réponse.', 's1')
        children = [p for p in (Path(a.state) / 'sessions').glob('*.jsonl')
                    if json.loads(p.read_text().splitlines()[0]).get('parent') == kernel]
        return f'pong-{run}' in r.get('text', '') and bool(children), \
            f"« {r.get('text', '')[:40]} » children={len(children)} tools={r.get('tools')}"

    def c_background():
        n0 = len(events())
        r = submit(f'Test technique : lance un sous-agent EN ARRIÈRE-PLAN (subagent avec run_in_background=true) avec '
                   f'la mission « Réponds seulement bg-{run} », puis termine ton tour tout de suite en répondant « lancé ». '
                   f'Quand tu seras réveillé avec sa réponse, rapporte-la seulement.', 'b1')
        woke, notices, last = wait_woken(n0, 'subagent-settled', f'bg-{run}')
        return woke, f"first=« {r.get('text', '')[:20]} » woke={woke} notices={len(notices)} last=« {last[:40]} »"

    def c_bash_job():
        n0 = len(events())
        r = submit(f'Test technique : avec bash en arrière-plan (run_in_background=true), lance `sleep 4; echo fini-{run}`, '
                   f'puis termine ton tour en répondant « lancé ». Quand tu seras réveillé, rapporte seulement la sortie.', 'j1')
        woke, notices, last = wait_woken(n0, 'tool-jobs', f'fini-{run}')
        return woke, f"first=« {r.get('text', '')[:20]} » woke={woke} notices={len(notices)} last=« {last[:40]} »"

    def _in_flight_bash(timeout: float = 90) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:          # wait until a bash call is journaled without its result
            evs = events()
            calls = {e['data'].get('callId') for e in evs if e['type'] == 'tool/call' and e['data'].get('name') == 'bash'}
            done = {e['data'].get('callId') for e in evs if e['type'] == 'tool/result'}
            if calls - done:
                time.sleep(1.5)                     # the approval is answered, the command is running
                return True
            time.sleep(0.5)
        return False

    def _healthy() -> None:
        for _ in range(60):
            try:
                if api.op({'op': 'health'}, timeout=3)[0] == 200:
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)

    def c_restart():
        """Graceful restart (SIGTERM): the running call is stopped and journaled `[interrupted]` by the engine itself,
        the turn is closed `interrupted` (engine_restart), the kernel's variables come back."""
        if not a.restart_unit:
            return True, 'skipped (no --restart-unit)'
        box: dict = {}
        th = threading.Thread(target=lambda: box.update(r=submit(
            'Test technique : exécute `sleep 40` dans bash au premier plan puis réponds « fini ».', 'r1', wait_ms=120000)),
            daemon=True)
        th.start()
        _in_flight_bash()
        n0 = len(events())
        subprocess.run(['systemctl', 'restart', a.restart_unit], check=True)
        _healthy()
        th.join(5)
        evs = events()[n0 - 1:]
        stopped = [e for e in evs if e['type'] == 'tool/result' and e['data'].get('name') == 'bash'
                   and ('[interrupted]' in (e['data'].get('content') or '') or e['data'].get('recovered'))]
        interrupted = [e for e in evs if e['type'] == 'turn/end' and e['data'].get('status') == 'interrupted']
        r2 = submit('Avec ton outil python, évalue `x` et réponds seulement le résultat.', 'r2')
        return bool(stopped) and bool(interrupted) and '41' in r2.get('text', ''), \
            f"stopped={len(stopped)} interrupted={len(interrupted)} x=« {r2.get('text', '')[:20]} »"

    def c_crash():
        """Hard crash (SIGKILL to the whole unit): at the next start the call without a result gets « résultat
        inconnu » (recovered), the turn is closed `interrupted`, and the side effect is NOT run again."""
        if not a.restart_unit:
            return True, 'skipped (no --restart-unit)'
        mark = Path(f'/tmp/walter-native-{run}.txt')
        box: dict = {}
        th = threading.Thread(target=lambda: box.update(r=submit(
            f'Test technique : exécute exactement `echo start >> {mark}; sleep 40; echo end >> {mark}` dans bash au '
            f'premier plan puis réponds « fini ».', 'k1', wait_ms=120000)), daemon=True)
        th.start()
        _in_flight_bash()
        n0 = len(events())
        subprocess.run(['systemctl', 'kill', '-s', 'SIGKILL', a.restart_unit], check=True)
        time.sleep(2)
        subprocess.run(['systemctl', 'restart', a.restart_unit], check=True)
        _healthy()
        th.join(5)
        time.sleep(5)
        evs = events()[n0 - 1:]
        unknown = [e for e in evs if e['type'] == 'tool/result' and e['data'].get('recovered')]
        interrupted = [e for e in evs if e['type'] == 'turn/end' and e['data'].get('status') == 'interrupted']
        lines = mark.read_text().split() if mark.exists() else []
        mark.unlink(missing_ok=True)
        return bool(unknown) and bool(interrupted) and lines == ['start'], \
            f"unknown={len(unknown)} interrupted={len(interrupted)} side_effect={lines}"

    for name, fn in (('python_persist', c_python_persist), ('python_tools', c_python_tools), ('subagent', c_subagent),
                     ('background', c_background), ('bash_job', c_bash_job), ('restart', c_restart),
                     ('crash', c_crash)):
        check(name, fn)
    stop.set()
    failed = [n for n, ok, _ in results if not ok]
    print(json.dumps({'session_id': sid, 'kernel': kernel, 'approvals_answered': len(answered),
                      'passed': len(results) - len(failed), 'failed': failed}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
