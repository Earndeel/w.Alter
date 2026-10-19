"""The active Walter instance: one person's identity, settings, accounts, learned skills and file state.

Software (``/walter/<module>``) is identical for every instance and carries defaults only; an instance
(``/instances/<id>`` on a host, ``/instance`` in a container) carries everything that belongs to one person
(DECISIONS.md 2026-10-19, "Walter produit : logiciel, instance, conteneurs"). Modules never name an instance
directory: they ask this resolver, as they ask ``walter_platform.paths`` for module roots.

Active instance: ``WALTER_INSTANCE`` (absolute path) → the one-line pointer ``/etc/walter/instance`` → ``/instance``.
Reading only: nothing here creates, moves or writes instance files.
"""
from __future__ import annotations

import os
import re
import stat
import tomllib
from pathlib import Path, PurePosixPath

from . import paths

DEFAULT_ROOT = '/instance'
POINTER = Path('/etc/walter/instance')
MANIFEST = 'instance.toml'
SCHEMA_VERSION = 1
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,62}\Z')
# Directories of an instance (design §1). bootstrap/ holds the only secrets kept outside the vault.
LAYOUT = ('soul', 'profile', 'profiles', 'config', 'accounts', 'skills', 'state', 'harness', 'workspace',
          'backups', 'logs', 'cache', 'bootstrap')
EXCLUDED_FROM_BACKUP = ('cache', 'workspace')
PLACEHOLDER = re.compile(r'\{\{\s*(owner|instance)\.([a-z_]+)\s*\}\}')
SECRET_KEYS = re.compile(r'(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key)')


def _pointer(pointer=None):
    p = Path(pointer or POINTER)
    try:
        value = p.read_text().strip()
    except OSError:
        return None
    return value or None


def root(*, pointer=None):
    """Root of the active instance (it may not exist yet: ``check`` says so)."""
    value = os.environ.get('WALTER_INSTANCE') or _pointer(pointer) or DEFAULT_ROOT
    return Path(str(paths._safe_absolute(value, 'WALTER_INSTANCE')))


def manifest(base=None):
    base = Path(base) if base else root()
    doc = tomllib.loads((base / MANIFEST).read_text())
    if doc.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('unsupported instance schema')
    if not isinstance(doc.get('id'), str) or not ID.match(doc['id']):
        raise ValueError('invalid instance id')
    owner = doc.get('owner')
    if not isinstance(owner, dict) or not isinstance(owner.get('address'), str) or not owner['address']:
        raise ValueError('instance owner needs an address form')
    return doc


def path(*parts, base=None):
    p = PurePosixPath(str(Path(base) if base else root()))
    for part in parts:
        p = p / paths.relative(part)
    return Path(str(p))


def state(module, *parts, base=None):
    return path('state', module, *parts, base=base)


def config(module, name, *, base=None, catalog=None, filesystem='/'):
    """A module setting: the instance override when present, else the module's shipped default."""
    override = path('config', module, name, base=base)
    if override.is_file():
        return override
    return paths.module_path(module, 'config', name, catalog=catalog, filesystem=filesystem)


def owner(base=None):
    """Who the instance serves, as the agents address them. Defaults keep the shipped software neutral."""
    o = dict(manifest(base)['owner'])
    o.setdefault('language', 'fr')
    o.setdefault('timezone', 'UTC')
    return o


def render(text, base=None):
    """Replace ``{{owner.address}}``, ``{{owner.language}}``, ``{{instance.id}}``… in shipped templates."""
    doc = manifest(base)
    values = {'owner': owner(base), 'instance': {'id': doc['id'], 'root': str(Path(base) if base else root())}}

    def sub(m):
        found = values[m.group(1)].get(m.group(2))
        if not isinstance(found, str):
            raise ValueError('unknown placeholder: ' + m.group(0))
        return found
    return PLACEHOLDER.sub(sub, text)


def markers(base=None):
    """Private markers of the instance: words that must never appear in shipped software."""
    doc = manifest(base)
    o = doc['owner']
    found = [o.get('address'), o.get('name'), *o.get('emails', [])]
    found += doc.get('privacy', {}).get('markers', [])
    return sorted({m for m in found if isinstance(m, str) and len(m) >= 3}, key=str.lower)


def _secret_like(doc, trail=()):
    """String values under secret-sounding keys (backup.<module> tables name modules, not secrets)."""
    for k, v in doc.items():
        if isinstance(v, dict):
            yield from _secret_like(v, trail + (k,))
        elif (isinstance(v, str) and v and SECRET_KEYS.search(k) and not k.endswith('_ref')
              and trail[:1] != ('backup',)):
            yield '.'.join(trail + (k,))


def check(base=None):
    """Read-only: manifest valid, layout present, bootstrap private, no secret value in instance.toml."""
    base = Path(base) if base else root()
    out = {'root': str(base), 'ok': False, 'problems': []}
    try:
        doc = manifest(base)
    except FileNotFoundError:
        out['problems'].append('no instance.toml')
        return out
    except (ValueError, tomllib.TOMLDecodeError) as exc:
        out['problems'].append('invalid instance.toml: ' + (str(exc) if type(exc) is ValueError else 'syntax'))
        return out
    out.update(id=doc['id'], owner_address=doc['owner']['address'])
    missing = [d for d in LAYOUT if not (base / d).is_dir()]
    if missing:
        out['problems'].append('missing directories: ' + ', '.join(missing))
    boot = base / 'bootstrap'
    if boot.is_dir() and stat.S_IMODE(boot.stat().st_mode) & 0o077:
        out['problems'].append('bootstrap/ must be private (0700)')
    leaked = list(_secret_like(doc))
    if leaked:
        out['problems'].append('secret-like keys in instance.toml (store a *_ref to the vault): ' + ', '.join(leaked))
    out['ok'] = not out['problems']
    return out


def show(base=None):
    base = Path(base) if base else root()
    doc = manifest(base)
    return {'id': doc['id'], 'root': str(base), 'owner': {k: v for k, v in owner(base).items() if k in
            ('address', 'language', 'timezone')}, 'software': doc.get('software', {}),
            'accounts': sorted(p.stem for p in (base / 'accounts').glob('*.toml')),
            'markers': len(markers(base))}
