import json
from pathlib import Path
import pytest
from walter_memory import backup_bundle as B


def contracts(root):
    # All configuration is synthetic; fixtures copy only public module contracts.
    source=Path('/opt/walter-core/modules')
    catalog=json.loads((source/'catalog.json').read_text())
    target=root/'opt/walter-core/modules'; target.mkdir(parents=True)
    (target/'catalog.json').write_text(json.dumps(catalog))
    (target/'registry.json').write_bytes((source/'registry.json').read_bytes())
    for item in catalog['modules']:
        dest=root/item['manifest'].lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(Path(item['manifest']).read_bytes())
    return catalog


def test_changed_owner_contract_blocks_backup_before_any_archive(tmp_path):
    root=tmp_path/'root'; catalog=contracts(root)
    assert B.contracts_check(root)['ok']
    path=root/catalog['modules'][0]['manifest'].lstrip('/')
    module=json.loads(path.read_text());module['backup_paths'].append('/new-required-state');path.write_text(json.dumps(module))
    archive=tmp_path/'bundle.tar'
    with pytest.raises(RuntimeError,match='differs from owner'):
        B.create(archive,root,[],[],False)
    assert not archive.exists()


def test_legacy_registry_is_supported_without_catalog(tmp_path):
    assert B.contracts_check(tmp_path)=={'legacy_registry':True}
