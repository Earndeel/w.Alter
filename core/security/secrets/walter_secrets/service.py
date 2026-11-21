"""Common, model-safe API. Use search/reference from MCP; execute ONLY locally.

References identify entries and fields, never contain values, and are not authorization
capabilities: the calling process still requires local access to the vault. No arbitrary
command execution is registered in MCP. Host shell/sandbox policy controls the local CLI.
"""
from __future__ import annotations
import os
import re
import signal
import subprocess
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID
from .vault import VAULT, SecretError, audit

API_VERSION = 1
REF_PREFIX = 'walter-secret://bitwarden/'
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _make_reference(item_id: str, field: str) -> str:
    UUID(item_id)
    return REF_PREFIX + item_id + '/' + quote(field, safe='')


def parse_reference(reference: str) -> tuple[str, str]:
    if not isinstance(reference, str):
        raise ValueError('secret reference must be a string')
    url = urlsplit(reference)
    parts = url.path.strip('/').split('/')
    if url.scheme != 'walter-secret' or url.netloc != 'bitwarden' or url.query or url.fragment or len(parts) != 2:
        raise ValueError('invalid secret reference')
    item_id, field = parts[0], unquote(parts[1])
    UUID(item_id)
    if not field or any(ord(c) < 32 for c in field):
        raise ValueError('invalid secret field')
    return item_id, field


def search(query: str = '', kind: str | None = None, limit: int = 20, *, vault=None) -> dict:
    vault = vault or VAULT
    if not isinstance(query, str) or len(query) > 500:
        raise ValueError('query must be a string of at most 500 characters')
    if kind not in (None, 'login', 'card', 'identity', 'note', 'ssh_key'):
        raise ValueError('unknown item type')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    items = vault.search(query, kind, limit)
    return {'api_version': API_VERSION, 'items': [{**i, 'handle': 'bw:' + i['id']} for i in items],
            'usage': 'Use secret_reference(item, field); bind the returned reference with walter-secret exec locally.'}


def reference(item: str, field: str, *, vault=None) -> dict:
    vault = vault or VAULT
    if not isinstance(item, str) or not isinstance(field, str) or not item or not field:
        raise ValueError('item and field are required')
    found = vault.find(item.removeprefix('bw:'))
    description = vault.describe(found)
    allowed = set(description['fields'])
    if description['type'] == 'login':
        allowed.add('uri')
    # The legacy CLI accepts custom fields with or without field: prefix.
    canonical = field if field in allowed else 'field:' + field
    if canonical not in allowed:
        raise ValueError('field is not available in the item metadata')
    return {'api_version': API_VERSION, 'reference': _make_reference(found['id'], canonical),
            'item_id': found['id'], 'field': canonical, 'value_disclosed': False}


def execute(argv: list[str], bindings: dict[str, str], *, timeout: float = 60,
            cwd: str | None = None, vault=None, audit_fn=None) -> dict:
    """Run locally with secret ENV bindings, never shell interpolation or raw output.

    The command can use credentials (HTTP headers, browser transport, etc.). It inherits
    the host's sandbox and user permissions. Output is always discarded: transformed or
    chunked secrets cannot be safely redacted in an arbitrary child process. No background
    service is started here; timeout terminates the child process group.
    """
    vault = vault or VAULT
    audit_fn = audit_fn or audit
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or '\x00' in a for a in argv):
        raise ValueError('argv must be a non-empty list of strings')
    if not isinstance(bindings, dict) or not bindings or len(bindings) > 32:
        raise ValueError('between 1 and 32 environment bindings are required')
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise ValueError('timeout must be between 0 and 300 seconds')
    resolved = {}
    for name, ref in bindings.items():
        if not isinstance(name, str) or not ENV_NAME.fullmatch(name):
            raise ValueError('invalid environment variable name')
        if name in {'HOME', 'PATH', 'PYTHONPATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'SHELL', 'BASH_ENV', 'ENV'}:
            raise ValueError('secret binding cannot replace a process control variable')
        item_id, field = parse_reference(ref)
        item = vault.find(item_id)
        value = vault.value(item_id, field)
        if '\x00' in value:
            raise ValueError('secret contains a byte incompatible with an environment binding')
        resolved[name] = value
        audit_fn('use', item, field, tool='local-exec')
    env = {**os.environ, **resolved}
    try:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 shell=False, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
            return {'success': code == 0, 'returncode': code, 'timed_out': False,
                    'output': 'discarded', 'bindings_used': len(bindings)}
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            return {'success': False, 'returncode': child.returncode, 'timed_out': True,
                    'output': 'discarded', 'bindings_used': len(bindings)}
    except OSError:
        raise SecretError('local secret execution failed (diagnostic suppressed)') from None
    finally:
        env.clear()
        resolved.clear()
