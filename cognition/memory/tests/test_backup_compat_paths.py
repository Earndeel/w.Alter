"""Archive and restore real synthetic files through the migrated module aliases."""
import io
import json
import tarfile

import pytest

from walter_memory import backup_bundle as B
from walter_memory.restore_drill import restore_tree


def migrated_tree(tmp_path):
    root = tmp_path / 'source'
    required = []
    for legacy, canonical, anchor in [
        ('core', 'core', 'server.py'),
        ('memory', 'memory', '.env'),
        ('raw-vault', 'memory/vault', 'rawvault.py'),
    ]:
        target = root / 'walter' / canonical
        target.mkdir(parents=True, exist_ok=True)
        (target / anchor).write_text('synthetic fixture, no credentials\n')
        alias = root / 'opt' / ('walter-' + legacy)
        alias.parent.mkdir(exist_ok=True)
        alias.symlink_to('../walter/' + canonical)
        required.append('opt/walter-' + legacy + '/' + anchor)
    sources = ['opt/walter-core', 'opt/walter-memory', 'opt/walter-raw-vault',
               'walter/core', 'walter/memory']
    return root, sources, required


def test_required_compat_children_are_proven_by_archived_alias_and_target(tmp_path):
    root, sources, required = migrated_tree(tmp_path)
    output = tmp_path / 'bundle.tar'
    result = B.create(output, root, sources, required, False)
    assert result['ok']
    assert B.verify(output, required)['ok']
    with tarfile.open(output) as archive:
        assert archive.getmember('opt/walter-memory').issym()
        assert archive.getmember('walter/memory/.env').isfile()
        assert 'opt/walter-memory/.env' not in archive.getnames()
    restored = tmp_path / 'restored'
    restore_tree(output, restored)
    for name in required:
        assert (restored / name).read_text() == 'synthetic fixture, no credentials\n'


def test_absolute_compat_link_is_resolved_inside_the_archive(tmp_path):
    root, sources, required = migrated_tree(tmp_path)
    output = tmp_path / 'relative.tar'
    B.create(output, root, sources, required, False)
    absolute = tmp_path / 'absolute.tar'
    with tarfile.open(output) as source, tarfile.open(absolute, 'w') as destination:
        for member in source:
            data = source.extractfile(member).read() if member.isfile() else None
            if member.name == 'opt/walter-memory':
                member.linkname = '/walter/memory'
            if member.name == B.MANIFEST:
                manifest = json.loads(data)
                manifest['entries']['opt/walter-memory']['target'] = '/walter/memory'
                data = json.dumps(manifest).encode()
                member.size = len(data)
            destination.addfile(member, io.BytesIO(data) if data is not None else None)
    assert B.verify(absolute, required)['ok']
    restored = tmp_path / 'restored'
    restore_tree(absolute, restored)
    assert (restored / 'opt/walter-memory/.env').read_text().startswith('synthetic fixture')


@pytest.mark.parametrize('target', ['../opt/walter-memory', '../../../outside',
                                    '../walter/missing', '../walter/memory/.env', ''])
def test_required_alias_rejects_cycle_escape_or_unarchived_target(tmp_path, target):
    root, sources, required = migrated_tree(tmp_path)
    output = tmp_path / 'bundle.tar'
    B.create(output, root, sources, required, False)
    altered = tmp_path / 'altered.tar'
    with tarfile.open(output) as source, tarfile.open(altered, 'w') as destination:
        for member in source:
            data = source.extractfile(member).read() if member.isfile() else None
            if member.name == 'opt/walter-memory':
                member.linkname = target
            if member.name == B.MANIFEST:
                manifest = json.loads(data)
                manifest['entries']['opt/walter-memory']['target'] = target
                data = json.dumps(manifest).encode()
                member.size = len(data)
            destination.addfile(member, io.BytesIO(data) if data is not None else None)
    with pytest.raises(ValueError, match='required paths missing'):
        B.verify(altered, required)
