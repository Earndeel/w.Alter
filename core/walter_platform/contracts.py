"""Owner-maintained module contracts and deterministic compatibility registry.

This compiler never imports module implementations or executes manifest commands.
The optional filesystem root supports offline restoration and fixture validation.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

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


def validate(module):
    """Validate a module's declarative contract, not its runtime qualification."""
    name = module.get('id', '')
    _require(isinstance(name, str) and IDENTIFIER.fullmatch(name), 'invalid module id')
    absolute_path(module.get('root'))
    for key in ('anchors', 'backup_paths', 'core_paths'):
        for value in _strings(module.get(key), key, nonempty=key != 'core_paths'):
            absolute_path(value)
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
    absolute_path(c.get('target_root'))
    for key in ('permissions', 'invariants', 'errors', 'cancellation', 'migrations'):
        _strings(c.get(key), key, nonempty=True)
    for p in _strings(c.get('config_paths'), 'config_paths'):
        absolute_path(p)
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
        path = absolute_path(entry.get('manifest'))
        _require(str(path) not in paths, 'duplicate contract file')
        resolved = (filesystem / str(path).lstrip('/')).resolve()
        _require(resolved.is_relative_to(filesystem), 'contract escapes filesystem root')
        module = validate(_read(resolved))
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
