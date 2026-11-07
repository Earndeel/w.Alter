"""Owner-maintained module contracts and deterministic compatibility registry.

This compiler never imports module implementations or executes manifest commands.
The optional filesystem root supports offline restoration and fixture validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

try:
    from . import paths as layout
except ImportError:
    # Loaded by file path, outside its package (backup bundles, restore drills): take the sibling resolver.
    import importlib.util as _importlib_util
    _spec = _importlib_util.spec_from_file_location('_walter_contracts_paths', Path(__file__).with_name('paths.py'))
    layout = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(layout)

CATALOG = Path(__file__).resolve().parent.parent / 'modules' / 'catalog.json'
IDENTIFIER = re.compile(r'[a-z][a-z0-9-]{0,63}\Z')
VERSION = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+\Z')
KINDS = {'foundation', 'capability', 'composition'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def absolute_path(value):
    _require(isinstance(value, str), 'contract path must be a string')
    p = Path(value)
    _require(p.is_absolute() and '..' not in p.parts and str(p) != '/', 'unsafe contract path')
    return p


def _strings(value, name, *, nonempty=False):
    _require(isinstance(value, list), 'contract list required: ' + name)
    _require(all(isinstance(v, str) and v.strip() for v in value), 'invalid contract list: ' + name)
    _require(len(value) == len(set(value)), 'duplicate contract value: ' + name)
    if nonempty:
        _require(bool(value), 'empty contract list: ' + name)
    return value


def _read(path):
    _require(path.stat().st_size <= 1024 * 1024, 'oversized contract')
    try:
        data = json.loads(path.read_text())
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('invalid contract JSON') from None
    _require(isinstance(data, dict), 'contract must be an object')
    return data


# In backup_paths: the locations the active instance declares for this module ([backup] <module> = [...] in
# instance.toml), e.g. historical data kept outside the instance. Never a path written in the software.
INSTANCE_BACKUP = '@instance:backup'


def instance_backup_paths(module):
    from . import instance
    try:
        declared = instance.manifest().get('backup', {}).get(module, [])
    except (OSError, ValueError):
        return []
    _require(isinstance(declared, list), 'instance backup paths must be a list')
    return [str(absolute_path(v)) for v in declared]


def contract_path(value):
    """Owner manifests: relative paths live inside the module, absolute ones are external to it."""
    _require(isinstance(value, str), 'contract path must be a string')
    if value.startswith('/'):
        return absolute_path(value)
    if value == INSTANCE_BACKUP:
        return PurePosixPath(value)
    if layout.is_instance_path(value) or value.startswith('~/'):
        return layout.join('/', value)
    try:
        return layout.relative(value)
    except ValueError:
        raise ValueError('unsafe contract path') from None


def validate(module, *, source=False):
    """Validate a module's declarative contract, not its runtime qualification.

    source=True accepts an owner manifest (paths relative to the module, no root); the default checks a
    compiled registry entry, where every path is absolute.
    """
    check = contract_path if source else absolute_path
    name = module.get('id', '')
    _require(isinstance(name, str) and IDENTIFIER.fullmatch(name), 'invalid module id')
    if not source or 'root' in module:
        absolute_path(module.get('root'))
    for key in ('anchors', 'backup_paths', 'core_paths'):
        for value in _strings(module.get(key), key, nonempty=key != 'core_paths'):
            check(value)
    for key in ('requires', 'optional', 'external', 'services', 'data', 'limitations'):
        _strings(module.get(key), key)
    _strings(module.get('interfaces'), 'interfaces', nonempty=True)
    _require(isinstance(module.get('bindings'), dict), 'bindings must be an object')
    c = module.get('contract')
    _require(isinstance(c, dict) and c.get('schema_version') == 1, 'unsupported module contract')
    _require(isinstance(c.get('version'), str) and VERSION.fullmatch(c['version']), 'invalid contract version')
    _require(c.get('owner') == name, 'contract owner must be its module')
    _require(c.get('kind') in KINDS, 'invalid contract kind')
    _require(isinstance(c.get('purpose'), str) and bool(c['purpose'].strip()), 'contract purpose required')
    check(c.get('target_root'))
    for key in ('permissions', 'invariants', 'errors', 'cancellation', 'migrations'):
        _strings(c.get(key), key, nonempty=True)
    for p in _strings(c.get('config_paths'), 'config_paths'):
        check(p)
    operations = c.get('operations')
    _require(isinstance(operations, list) and bool(operations), 'contract operations required')
    op_ids = set()
    for op in operations:
        _require(isinstance(op, dict), 'invalid operation')
        op_id = op.get('id', '')
        _require(isinstance(op_id, str) and IDENTIFIER.fullmatch(op_id), 'invalid operation id')
        _require(op_id not in op_ids, 'duplicate operation')
        op_ids.add(op_id)
        _require(op.get('access') in {'read', 'write', 'execute'}, 'invalid operation access')
        _require(op.get('transport') in {'library', 'cli', 'http', 'mcp', 'event', 'sip', 'renderer'}, 'invalid transport')
        _require(isinstance(op.get('interface'), str) and bool(op['interface']), 'operation interface required')
        timeout = op.get('timeout_seconds')
        _require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 10800, 'invalid operation timeout')
        _require(op.get('timeout_status') in {'implemented', 'target'}, 'timeout evidence status required')
    resources = c.get('resources')
    _require(isinstance(resources, list), 'contract resources required')
    for item in resources:
        _require(isinstance(item, dict) and isinstance(item.get('id'), str) and bool(item['id']), 'invalid resource')
        _require(item.get('role') in {'owner', 'consumer'}, 'invalid resource role')
        _require(isinstance(item.get('owner'), str) and IDENTIFIER.fullmatch(item['owner']), 'resource owner required')
        _require(item['role'] != 'owner' or item['owner'] == name, 'resource ownership mismatch')
        _require(item.get('durability') in {'canonical', 'projection', 'configuration', 'ephemeral', 'external'}, 'invalid resource durability')
    recovery = c.get('recovery')
    _require(isinstance(recovery, dict), 'recovery contract required')
    for key in ('backup', 'restore', 'verification'):
        _strings(recovery.get(key), 'recovery.' + key, nonempty=True)
    if 'presentation' in module:
        _presentation(module['presentation'], check)
    scenarios = c.get('acceptance')
    _require(isinstance(scenarios, list) and bool(scenarios), 'acceptance scenarios required')
    ids = set()
    for item in scenarios:
        _require(isinstance(item, dict), 'invalid acceptance scenario')
        ident = item.get('id', '')
        _require(isinstance(ident, str) and IDENTIFIER.fullmatch(ident) and ident not in ids, 'invalid acceptance scenario id')
        ids.add(ident)
        _require(isinstance(item.get('assertion'), str) and bool(item['assertion']), 'acceptance assertion required')
        _require(item.get('scope') in {'unit', 'integration', 'live', 'recovery'}, 'invalid acceptance scope')
    return module


PRESENTATION_KEYS = {'audience', 'title', 'order', 'summary', 'manifest', 'manifest_command', 'guide', 'tools', 'index'}
TOOL = re.compile(r'[a-z][a-z0-9_]{0,63}\Z')


def _presentation(value, check):
    """How a module presents itself to agents. Texts live in the module folder (manifest/), never in the contract:
    summary = M0, one line (what it does + the tool to open), always present; manifest = M1, operational brief
    (what it is, organisation, how to use it); manifest_command = a live part the module generates and appends to M1;
    guide = M2, full documentation on demand; index = what the module contains (separate axis, module_index)."""
    _require(isinstance(value, dict) and set(value) <= PRESENTATION_KEYS, 'invalid presentation')
    _require(value.get('audience') in {'agent', 'internal'}, 'presentation audience required')
    _require(isinstance(value.get('title'), str) and bool(value['title'].strip()), 'presentation title required')
    _require(type(value.get('order', 50)) is int and 0 <= value.get('order', 50) <= 999, 'invalid presentation order')
    check(value.get('summary'))   # M0: one line, always present
    check(value.get('manifest'))  # M1
    if 'guide' in value:          # M2
        check(value['guide'])
    if 'manifest_command' in value:
        _strings(value['manifest_command'], 'presentation.manifest_command', nonempty=True)
    for tool in _strings(value.get('tools'), 'presentation.tools'):
        _require(TOOL.fullmatch(tool), 'invalid presentation tool')
    index = value.get('index')
    if index is not None:
        _require(isinstance(index, dict) and set(index) <= {'command', 'section_arg', 'paged', 'sections'},
                 'invalid presentation index')
        _strings(index.get('command'), 'presentation.index.command', nonempty=True)
        _require(isinstance(index.get('section_arg', ''), str), 'invalid index section argument')
        _require(isinstance(index.get('paged', False), bool), 'invalid index paging flag')
        _require(isinstance(index.get('sections', ''), str), 'invalid index sections description')


def expand(manifest, root, target_root):
    """Compiled registry entry of an owner manifest located at ``root``. Absolute manifests are unchanged."""
    _require(isinstance(manifest, dict), 'contract must be an object')
    raw = json.loads(json.dumps(manifest))
    base = PurePosixPath(str(root))
    out = {'id': raw.pop('id', None), 'root': str(base)}
    raw.pop('root', None)
    for key in ('anchors', 'backup_paths', 'core_paths'):
        if isinstance(raw.get(key), list):
            expanded = []
            for v in raw[key]:
                if key == 'backup_paths' and v == INSTANCE_BACKUP:
                    expanded += instance_backup_paths(out['id'])
                else:
                    expanded.append(str(layout.join(base, v)))
            raw[key] = expanded
    pres = raw.get('presentation')
    if isinstance(pres, dict):
        for key in ('summary', 'manifest', 'guide'):
            if isinstance(pres.get(key), str):
                pres[key] = str(layout.join(base, pres[key]))
    c = raw.get('contract')
    if isinstance(c, dict):
        if isinstance(c.get('config_paths'), list):
            c['config_paths'] = [str(layout.join(base, v)) for v in c['config_paths']]
        c['target_root'] = str(target_root)
    out.update(raw)
    return out


def _manifest(entry, filesystem):
    """(manifest path, compiled module) for a catalog entry, in either catalog form."""
    if str(entry.get('manifest', '')).startswith('/'):
        # Catalog v1 form (older archives): absolute manifest holding absolute paths.
        path = absolute_path(entry.get('manifest'))
        resolved = (filesystem / str(path).lstrip('/')).resolve()
        _require(resolved.is_relative_to(filesystem), 'contract escapes filesystem root')
        raw = _read(resolved)
        if 'root' in raw:
            return path, validate(raw)
        # Relative owner manifest listed by an absolute path: the module root holds its contracts/ folder.
        _require(path.parent.name == 'contracts', 'relative manifest must live in its module contracts folder')
        raw = validate(raw, source=True)
        target = raw['contract']['target_root']
        target = absolute_path(target) if target.startswith('/') else layout.walter_root() / layout.relative(target)
        return path, validate(expand(raw, path.parent.parent, target))
    _require(isinstance(entry.get('target'), str), 'catalog target required')
    if entry.get('legacy') is not None:
        absolute_path(entry['legacy'])
    base = PurePosixPath(str(layout.resolve(entry, filesystem=filesystem)))
    path = base / layout.relative(entry.get('manifest', ''))
    resolved = (filesystem / str(path).lstrip('/')).resolve()
    _require(resolved.is_relative_to(filesystem), 'contract escapes filesystem root')
    raw = validate(_read(resolved), source=True)
    target = layout.target_root(entry)
    _require(raw['contract']['target_root'] in (entry['target'], str(target)), 'contract target differs from catalog')
    _require(raw.get('root') in (None, str(base)), 'contract root differs from its location')
    return Path(str(path)), validate(expand(raw, base, target))


def compile_registry(catalog=None, *, root='/'):
    """Compile owner manifests into the v1 registry consumed by existing clients."""
    doc = _read(Path(catalog or CATALOG))
    _require(doc.get('schema_version') == 1, 'unsupported contract catalog')
    entries = doc.get('modules')
    _require(isinstance(entries, list) and bool(entries), 'empty contract catalog')
    filesystem = Path(root).resolve()
    modules, ids, paths = [], set(), set()
    for entry in entries:
        _require(isinstance(entry, dict), 'invalid catalog entry')
        ident = entry.get('id')
        _require(isinstance(ident, str) and IDENTIFIER.fullmatch(ident) and ident not in ids, 'duplicate or invalid catalog module')
        path, module = _manifest(entry, filesystem)
        _require(str(path) not in paths, 'duplicate contract file')
        _require(module['id'] == ident, 'catalog/module identity mismatch')
        _require(path.is_relative_to(absolute_path(module['root'])), 'manifest must belong to module root')
        _require(str(path) in module['anchors'], 'manifest must be a required backup anchor')
        modules.append(module)
        ids.add(ident)
        paths.add(str(path))
    owners = {}
    by_id = {m['id']: m for m in modules}
    for module in modules:
        for dep in module['requires'] + module['optional']:
            _require(dep in ids and dep != module['id'], 'unknown or self dependency')
        _require(not set(module['requires']).intersection(module['optional']), 'dependency cannot be required and optional')
        for resource in module['contract']['resources']:
            _require(resource['owner'] in ids, 'unknown resource owner')
            if resource['role'] == 'owner':
                _require(resource['id'] not in owners, 'resource has multiple owners')
                owners[resource['id']] = module['id']
    for module in modules:
        for resource in module['contract']['resources']:
            _require(owners.get(resource['id']) == resource['owner'], 'resource lacks matching owner declaration')
    visited, active = set(), set()
    def visit(ident):
        _require(ident not in active, 'required module dependency cycle')
        if ident in visited:
            return
        active.add(ident)
        for dep in by_id[ident]['requires']:
            visit(dep)
        active.remove(ident)
        visited.add(ident)
    for ident in sorted(ids):
        visit(ident)
    return {'version': 1, 'modules': sorted(modules, key=lambda m: m['id'])}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def check(catalog=None, *, root='/', registry=None):
    catalog = Path(catalog or CATALOG)
    compiled = compile_registry(catalog, root=root)
    registry = Path(registry or catalog.with_name('registry.json'))
    matches = registry.exists() and _read(registry) == compiled
    return {'ok': matches, 'modules': len(compiled['modules']), 'registry_matches_contracts': matches,
            'sha256': hashlib.sha256(encoded(compiled)).hexdigest(),
            'scope': 'schema, ownership, required dependency DAG, generated registry; runtime qualification is separate'}


def render_markdown(value):
    """Documentation is rendered from the exact same contracts as backups."""
    rows = ['# Contrats des modules Walter', '',
            'Généré depuis les manifestes propriétaires. Les scénarios décrivent les critères ; leur réussite est mesurée séparément.', '',
            '| Module | Niveau | Responsabilité | Dépendances obligatoires |', '|---|---|---|---|']
    def cell(text):
        return str(text).replace('|', '\\|').replace('\n', ' ')
    for m in value['modules']:
        c = m['contract']
        rows.append('| ' + ' | '.join(map(cell, (m['id'], c['kind'], c['purpose'], ', '.join(m['requires']) or '—'))) + ' |')
    for m in value['modules']:
        c = m['contract']
        rows += ['', '## ' + m['id'], '', c['purpose'], '', 'Contrat ' + c['version'] + '; propriétaire : ' + c['owner'] + '.',
                 'Racine actuelle : `' + m['root'] + '`. Cible : `' + c['target_root'] + '`.', '',
                 'Interfaces : ' + ', '.join(m['interfaces']) + '.', '', '**Critères de validation :**', '']
        rows += ['- ' + x['assertion'] + ' (' + x['scope'] + ')' for x in c['acceptance']]
        rows += ['', '**Limites déclarées :**', '']
        rows += ['- ' + text for text in (m['limitations'] or ['Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.'])]
    return '\n'.join(rows) + '\n'
