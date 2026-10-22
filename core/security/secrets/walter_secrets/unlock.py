"""Bitwarden bootstrap independent of an agent runtime. No values in diagnostics.

Only --print/--sync return a local credential to another process, never an agent.
A disconnected account is re-authenticated using its configured bootstrap credentials.
This preserves the existing local helper behavior; MFA prompts still fail closed.
"""
from __future__ import annotations
import fcntl
import hashlib
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


def fingerprint(token: str) -> str:
    """Not a secret: lets a caller say which session failed without passing the session itself."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def session(stale: str | None = None) -> str:
    """The cached session, or a new one. Unlocking happens under an exclusive lock and re-reads the cache first:
    every `bw unlock` invalidates the previous session, so two processes unlocking at once used to leave a dead
    session in the cache (2026-10-22: Cloudflare, Telegram and Beeper down until the cache was moved aside).
    `stale` = fingerprint of a session a bw command just refused ("Vault is locked"): it is never returned again."""
    cache = settings.SESSION
    if stale is None and cache.exists():
        cached = cache.read_text().strip().removeprefix('export BW_SESSION=')
        if cached and time.time() - cache.stat().st_mtime < 28800:
            return cached
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(cache.with_name(cache.name + '.lock'), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _session_locked(cache, stale)
    finally:
        os.close(lock)


def _session_locked(cache: Path, stale: str | None) -> str:
    if cache.exists():
        cached = cache.read_text().strip().removeprefix('export BW_SESSION=')
        if cached and stale is not None and fingerprint(cached) != stale:
            return cached                       # another process renewed it while we waited for the lock
        if cached and stale is None:
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
        bootstrap = json.loads(raw)['services']['bitwarden']
        master = bootstrap['master_password']
    except (KeyError, ValueError, TypeError):
        raise UnlockError('Bitwarden bootstrap credential unavailable') from None
    # Preserve the former bootstrap helper's reconnect behavior. The account password
    # remains in the child environment, and no command output crosses the local helper.
    status = json.loads(_run(['bw', 'status', '--nointeraction']))
    if status.get('status') == 'unauthenticated':
        server = settings.setting('bitwarden', 'server', bootstrap.get('server_url'))
        email = settings.setting('bitwarden', 'email', bootstrap.get('email'))
        if not server or not email:
            raise UnlockError('Bitwarden account configuration unavailable')
        _run(['bw', 'config', 'server', server, '--nointeraction'])
        _run(['bw', 'login', email, '--passwordenv', 'WALTER_BW_MASTER', '--nointeraction'],
             env={**os.environ, 'WALTER_BW_MASTER': master, 'BW_NOINTERACTION': 'true'})
    # Environment prevents the master password from appearing in process argv.
    token = _run(['bw', 'unlock', '--passwordenv', 'WALTER_BW_MASTER', '--raw', '--nointeraction'],
                 env={**os.environ, 'WALTER_BW_MASTER': master, 'BW_NOINTERACTION': 'true'})
    del raw, master, bootstrap
    if not token or '\n' in token:
        raise UnlockError('Bitwarden returned an invalid session')
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
        elif argv in (['--print'], ['--sync'], ['--renew']):
            # --renew: the cached session was refused; its fingerprint comes in WALTER_BW_STALE (never the session)
            token = session(os.environ.get('WALTER_BW_STALE') or 'unknown') if argv == ['--renew'] else session()
            if argv == ['--sync']:
                _run(['bw', 'sync', '--nointeraction'], env={**os.environ, 'BW_SESSION': token})
            print(token)
        else:
            print('usage: bw-unlock --print|--sync|--renew|--check', file=sys.stderr)
            return 2
    except (UnlockError, OSError, ValueError):
        print('walter-secrets: Bitwarden unlock failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
