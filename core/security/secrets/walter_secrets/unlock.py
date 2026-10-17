"""Bitwarden bootstrap independent of an agent runtime. No values in diagnostics.

Only --print/--sync return a local credential to another process, never an agent.
The account must already be logged in; account creation/login remains maintenance.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from . import settings


class UnlockError(RuntimeError):
    pass


def _run(argv, *, env=None):
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UnlockError('Bitwarden bootstrap command unavailable') from None
    if result.returncode:
        raise UnlockError('Bitwarden bootstrap command failed')
    return result.stdout.strip()


def session() -> str:
    cache = settings.SESSION
    if cache.exists():
        cached = cache.read_text().strip().removeprefix('export BW_SESSION=')
        if cached:
            if time.time() - cache.stat().st_mtime < 28800:
                return cached
            try:
                status = json.loads(_run(['bw', 'status', '--nointeraction'],
                                         env={**os.environ, 'BW_SESSION': cached}))
                if status.get('status') == 'unlocked':
                    cache.touch()
                    return cached
            except (UnlockError, ValueError):
                pass
    raw = _run(['age', '-d', '-i', str(settings.VAULT_KEY), str(settings.VAULT_ENC)])
    try:
        master = json.loads(raw)['services']['bitwarden']['master_password']
    except (KeyError, ValueError, TypeError):
        raise UnlockError('Bitwarden bootstrap credential unavailable') from None
    # Environment prevents the master password from appearing in process argv.
    token = _run(['bw', 'unlock', '--passwordenv', 'WALTER_BW_MASTER', '--raw', '--nointeraction'],
                 env={**os.environ, 'WALTER_BW_MASTER': master, 'BW_NOINTERACTION': 'true'})
    del raw, master
    if not token or '\n' in token:
        raise UnlockError('Bitwarden returned an invalid session')
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = cache.with_name(cache.name + f'.tmp-{os.getpid()}')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(token)
        os.replace(temporary, cache)
    finally:
        temporary.unlink(missing_ok=True)
    return token


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv == ['--check']:
            status = json.loads(_run(['bw', 'status', '--nointeraction']))
            print(json.dumps({'status': status.get('status')}))
        elif argv in (['--print'], ['--sync']):
            token = session()
            if argv == ['--sync']:
                _run(['bw', 'sync', '--nointeraction'], env={**os.environ, 'BW_SESSION': token})
            print(token)
        else:
            print('usage: bw-unlock --print|--sync|--check', file=sys.stderr)
            return 2
    except (UnlockError, OSError, ValueError):
        print('walter-secrets: Bitwarden unlock failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
