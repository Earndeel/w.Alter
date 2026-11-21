import json
from pathlib import Path
import pytest
from walter_memory import backup_bundle as B


def manifest(item):
    # Catalog entries name a module-relative manifest; the module is at its /walter target once moved.
    if item['manifest'].startswith('/'):return Path(item['manifest'])
    target=Path('/walter')/item['target']
    return (target if target.is_dir() and not target.is_symlink() else Path(item['legacy']))/item['manifest']


def contracts(root):
    # All configuration is synthetic; fixtures copy only public module contracts.
    source=Path('/opt/walter-core/modules')
    catalog=json.loads((source/'catalog.json').read_text())
    target=root/'opt/walter-core/modules'; target.mkdir(parents=True)
    (target/'catalog.json').write_text(json.dumps(catalog))
    (target/'registry.json').write_bytes((source/'registry.json').read_bytes())
    for item in catalog['modules']:
        dest=root/str(manifest(item)).lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(manifest(item).read_bytes())
    return catalog


def _drift(root, catalog, value):
    path=root/str(manifest(catalog['modules'][0])).lstrip('/')
    module=json.loads(path.read_text());module['backup_paths'].append(value);path.write_text(json.dumps(module))


def test_changed_owner_contract_gives_a_degraded_backup_covering_both(tmp_path):
    # Owner decision 2026-10-27: a registry drift must not leave Walter without a backup.
    root=tmp_path/'root'; catalog=contracts(root)
    assert B.contracts_check(root)['ok']
    _drift(root, catalog, '/new-required-state')
    state=B.contracts_check(root)
    assert state['degraded'] and 'new-required-state' in state['rendered_paths']
    assert 'new-required-state' in B.module_backup_paths(root)          # registry in place ∪ contracts
    archive=tmp_path/'bundle.tar'
    B.create(archive,root,[],[],False)
    assert archive.exists()
    import tarfile
    with tarfile.open(archive) as t:
        recorded=json.loads(t.extractfile(B.MANIFEST).read())['contract_check']
    assert recorded['degraded'] and recorded['registry_matches_contracts'] is False


def test_unsafe_contract_path_still_blocks_the_backup(tmp_path):
    root=tmp_path/'root'; catalog=contracts(root)
    _drift(root, catalog, 'relative/../escape')
    with pytest.raises(RuntimeError):
        B.module_backup_paths(root)


def test_legacy_registry_is_supported_without_catalog(tmp_path):
    assert B.contracts_check(tmp_path)=={'legacy_registry':True}
