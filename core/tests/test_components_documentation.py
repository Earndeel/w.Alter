"""E0 (2026-11-09): components in module contracts, vision targets in the catalog, documentation invariants.
Fixtures only; the live registry is read, never written."""
import copy
import json
from pathlib import Path

import pytest

from walter_platform import contracts, documentation, paths

CORE = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((CORE / 'modules/registry.json').read_text())


def module(ident):
    return copy.deepcopy(next(m for m in REGISTRY['modules'] if m['id'] == ident))


def test_every_module_declares_components_with_a_real_status():
    for m in REGISTRY['modules']:
        assert m.get('components'), m['id']
        for c in m['components']:
            assert c['status'] in contracts.COMPONENT_STATUS
            assert c['status'] == 'planned' or c.get('readme'), (m['id'], c['id'])


@pytest.mark.parametrize('bad', [
    {'id': 'X', 'path': 'a', 'role': 'r', 'status': 'active', 'readme': 'README.md'},          # invalid id
    {'id': 'x', 'path': '../escape', 'role': 'r', 'status': 'active', 'readme': 'README.md'},  # traversal
    {'id': 'x', 'path': 'a', 'role': 'r', 'status': 'done', 'readme': 'README.md'},           # unknown status
    {'id': 'x', 'path': 'a', 'role': 'r', 'status': 'active'},                                # readme required
    {'id': 'x', 'path': 'a', 'role': '', 'status': 'planned'},                                # role required
    {'id': 'x', 'path': 'a', 'role': 'r', 'status': 'planned', 'extra': 1},                   # closed keys
    {'id': 'x', 'path': 'a', 'role': 'r', 'status': 'planned', 'interfaces': [{'transport': 'smoke', 'interface': 'i'}]},
])
def test_invalid_components_are_refused(bad):
    m = module('core')
    m['components'] = [bad]
    with pytest.raises(ValueError):
        contracts._components(m['components'], 'core', contracts.contract_path)


def test_duplicate_component_ids_are_refused():
    c = {'id': 'x', 'path': 'a', 'role': 'r', 'status': 'planned'}
    with pytest.raises(ValueError):
        contracts._components([c, dict(c)], 'core', contracts.contract_path)


def test_component_paths_are_expanded_like_anchors():
    raw = {'id': 'core', 'components': [{'id': 'x', 'path': 'engine', 'role': 'r', 'status': 'planned',
                                         'readme': 'engine/README.md', 'contracts': ['engine/contracts/a.json']}]}
    out = contracts.expand(raw, '/w/core', '/w/core')
    c = out['components'][0]
    assert (c['path'], c['readme'], c['contracts']) == ('/w/core/engine', '/w/core/engine/README.md',
                                                         ['/w/core/engine/contracts/a.json'])


def test_catalog_vision_targets_are_reported_but_never_used_to_resolve():
    layout = paths.layout()
    assert layout['vision']['declared'] == len(layout['modules'])
    router = next(r for r in layout['modules'] if r['id'] == 'router')
    assert router['vision_target'].endswith('/cognition/router') and router['root'].endswith('/router')
    assert paths.module_root('router') == Path(router['root'])        # resolution unchanged until E9


def test_header_fields_accept_french_and_english_labels():
    fr = '| | |\n|---|---|\n| **Rôle** | x |\n| **Propriétaire** | y |\n| **État** | z |\n| **Ne fait pas** | a |\n| **Contrats** | b |\n'
    en = '| **Role** | x |\n| **Owner** | y |\n| **Status** | z |\n'
    assert documentation.header_fields(fr) == set(documentation.HEADER)
    assert documentation.header_fields(en) == {'role', 'owner', 'status'}


def test_documentation_scan_reports_missing_component_paths(tmp_path):
    reg = {'version': 1, 'modules': [module('runtime')]}
    reg['modules'][0]['requires'] = []
    reg['modules'][0]['components'] = [{'id': 'ghost', 'path': str(tmp_path / 'nope'), 'role': 'r',
                                        'status': 'active', 'readme': str(tmp_path / 'README.md')}]
    f = tmp_path / 'registry.json'
    f.write_text(json.dumps(reg))
    out = documentation.scan(f)
    kinds = {x['kind'] for x in out['findings']}
    assert {'component_path_missing', 'component_readme_missing'} <= kinds and not out['ok']


def test_live_registry_has_no_blocking_documentation_finding():
    assert documentation.scan()['ok']
