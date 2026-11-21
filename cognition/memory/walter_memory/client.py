"""Dependency-free transport to Walter Memory; no policy or retrieval duplicated here."""
from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
URL = 'http://127.0.0.1:8890/v1/agent-memory'


def token():
    info = ENV_FILE.stat()
    if info.st_uid not in {0, os.getuid()} or stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError('unsafe Walter Memory credential file permissions')
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith('WALTER_MEMORY_GATEWAY_TOKEN='):
            value = line.split('=', 1)[1].strip().strip('\"').strip("'")
            if value:
                return value
    raise PermissionError('Walter Memory credential unavailable')


def configured():
    try:
        return bool(token())
    except (OSError, PermissionError):
        return False


def call(method, args, *, caller='walter-port', timeout=8):
    request = urllib.request.Request(URL, method='POST',
        data=json.dumps({'version': 1, 'method': method, 'args': args, 'caller': caller}, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token()})
    try:
        # Never retry a write automatically: a timed-out retain may have committed.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read(2 * 1024 * 1024))
        if not isinstance(result, dict):
            raise ValueError('invalid memory response')
        return result
    except Exception:
        return {'status': 'error', 'backend': 'walter-memory',
                'code': 'memory_unavailable', 'text': 'Walter Memory unavailable; no alternative backend was used.'}
