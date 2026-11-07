"""Where each Walter module lives: one resolver for modules, harness adapters and scripts.

Target layout (DECISIONS.md 2026-10-19): ``WALTER_ROOT`` (default ``/walter``) / <target>, nested by
ownership (``router/llm``, ``memory/vault``). Until a module is moved it is found at its legacy root
(``/opt/walter-<x>``), which becomes a compatibility link once the module has moved.

The catalog (``modules/catalog.json``) is the only table of targets and legacy roots. Resolution never
imports module code and accepts an alternate filesystem root (restore drills, release bundles).
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath

DEFAULT_ROOT = '/walter'
CATALOG = Path(__file__).resolve().parent.parent / 'modules' / 'catalog.json'


def _safe_absolute(value, what):
    if not isinstance(value, str) or not value:
        raise ValueError(what + ' must be a path string')
    p = PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts or str(p) == '/':
        raise ValueError('unsafe ' + what)
    return p


def relative(value):
    """A path inside a module: relative, no traversal. '.' designates the module root itself."""
    if not isinstance(value, str) or not value:
        raise ValueError('module path must be a path string')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('unsafe module-relative path')
    return p


def walter_root():
    return _safe_absolute(os.environ.get('WALTER_ROOT') or DEFAULT_ROOT, 'WALTER_ROOT')


INSTANCE = '@instance'


def is_instance_path(value):
    return isinstance(value, str) and (value == INSTANCE or value.startswith(INSTANCE + '/'))


def join(root, value):
    """Expand a contract path: absolute values are external to the module and kept as they are;
    ``@instance[/sub]`` designates the active instance (walter_platform.instance), never a fixed directory;
    ``~/sub`` is the service user's home (never a literal /root)."""
    if isinstance(value, str) and value.startswith('/'):
        return _safe_absolute(value, 'contract path')
    if isinstance(value, str) and value.startswith('~/'):
        return _safe_absolute(str(Path.home() / relative(value[2:])), 'contract path')
    if is_instance_path(value):
        from . import instance
        rest = value[len(INSTANCE):].lstrip('/')
        base = PurePosixPath(str(instance.root()))
        return base / relative(rest) if rest else base
    rel = relative(value)
    return PurePosixPath(root) if str(rel) == '.' else PurePosixPath(root) / rel


def _catalog(catalog=None):
    path = Path(catalog or CATALOG)
    doc = json.loads(path.read_text())
    if doc.get('schema_version') != 1:
        raise ValueError('unsupported contract catalog')
    return {e['id']: e for e in doc.get('modules', []) if isinstance(e, dict) and isinstance(e.get('id'), str)}


def entry(name, catalog=None):
    """A catalog entry by id, or by a former id kept in ``aliases`` (walter-backup became ops on 2026-10-29)."""
    entries = _catalog(catalog)
    found = entries.get(name) or next((e for e in entries.values() if name in (e.get('aliases') or [])), None)
    if found is None:
        raise ValueError('unknown Walter module: ' + str(name))
    return found


def target_root(item):
    """Where the module belongs in the target layout (whether or not it has moved yet)."""
    return walter_root() / relative(item['target'])


def legacy_root(item):
    value = item.get('legacy')
    return _safe_absolute(value, 'legacy module root') if value else None


def _on(filesystem, p):
    return Path(filesystem) / str(p).lstrip('/')


def resolve(item, *, filesystem='/'):
    """Current root of a catalog entry: its target once moved, else its legacy root, else the target."""
    target = target_root(item)
    real = _on(filesystem, target)
    if real.is_dir() and not real.is_symlink():
        return target
    legacy = legacy_root(item)
    if legacy is not None and _on(filesystem, legacy).is_dir():
        return legacy
    return target


def module_root(name, *, catalog=None, filesystem='/'):
    return Path(str(resolve(entry(name, catalog), filesystem=filesystem)))


def module_path(name, *parts, catalog=None, filesystem='/'):
    root = PurePosixPath(str(module_root(name, catalog=catalog, filesystem=filesystem)))
    for part in parts:
        root = root / relative(part)
    return Path(str(root))


def layout(*, catalog=None, filesystem='/'):
    """Migration view: where every module is now, where it belongs, and whether its legacy link is in place."""
    rows = []
    for name, item in sorted(_catalog(catalog).items()):
        target, legacy = target_root(item), legacy_root(item)
        current = resolve(item, filesystem=filesystem)
        link = None
        if legacy is not None and current == target:
            p = _on(filesystem, legacy)
            link = 'compat-link' if p.is_symlink() and p.resolve() == _on(filesystem, target).resolve() else (
                'absent' if not p.exists() and not p.is_symlink() else 'conflict')
        extra = {}
        for value in item.get('compat_links') or []:               # former names kept as links (renamed modules)
            p = _on(filesystem, _safe_absolute(value, 'compatibility link'))
            extra[value] = ('compat-link' if p.is_symlink() and p.resolve() == _on(filesystem, target).resolve()
                            else 'absent' if not p.exists() and not p.is_symlink() else 'conflict')
        rows.append({'id': name, 'root': str(current), 'target': str(target),
                     'legacy': str(legacy) if legacy else None, 'moved': current == target, 'legacy_link': link,
                     **({'aliases': item['aliases']} if item.get('aliases') else {}),
                     **({'compat_links': extra} if extra else {})})
    return {'walter_root': str(walter_root()), 'modules': rows,
            'ok': all(r['legacy_link'] in (None, 'compat-link', 'absent')
                      and all(v in ('compat-link', 'absent') for v in (r.get('compat_links') or {}).values())
                      for r in rows)}
