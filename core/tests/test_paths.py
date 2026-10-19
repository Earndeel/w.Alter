import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from walter_platform import contracts, paths


class PathResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fs = Path(self.temp.name)
        self.catalog = self.fs / 'catalog.json'
        self.entries = [
            {'id': 'colab', 'target': 'colab', 'legacy': '/opt/walter-colab', 'manifest': 'contracts/colab.json'},
            {'id': 'memory', 'target': 'memory', 'legacy': '/opt/walter-memory', 'manifest': 'contracts/memory.json'},
            {'id': 'raw-vault', 'target': 'memory/vault', 'legacy': '/opt/walter-raw-vault', 'manifest': 'contracts/raw-vault.json'},
            {'id': 'llm', 'target': 'router/llm', 'legacy': '/opt/walter-llm', 'manifest': 'contracts/llm.json'},
        ]
        self.catalog.write_text(json.dumps({'schema_version': 1, 'modules': self.entries}))
        env = mock.patch.dict(os.environ, {'WALTER_ROOT': '/walter'})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.temp.cleanup()

    def mkdir(self, p):
        (self.fs / p.lstrip('/')).mkdir(parents=True, exist_ok=True)

    def root(self, name):
        return str(paths.module_root(name, catalog=self.catalog, filesystem=self.fs))

    def test_legacy_root_until_moved_then_target(self):
        self.mkdir('/opt/walter-colab')
        self.assertEqual(self.root('colab'), '/opt/walter-colab')
        (self.fs / 'opt/walter-colab').rename(self.fs / 'walter-colab-tmp')
        self.mkdir('/walter')
        (self.fs / 'walter-colab-tmp').rename(self.fs / 'walter/colab')
        (self.fs / 'opt/walter-colab').symlink_to(self.fs / 'walter/colab')
        self.assertEqual(self.root('colab'), '/walter/colab')
        row = next(r for r in paths.layout(catalog=self.catalog, filesystem=self.fs)['modules'] if r['id'] == 'colab')
        self.assertEqual((row['moved'], row['legacy_link']), (True, 'compat-link'))

    def test_missing_module_resolves_to_its_install_target(self):
        self.assertEqual(self.root('llm'), '/walter/router/llm')

    def test_nested_target_waits_for_its_own_move(self):
        self.mkdir('/walter/memory')
        self.mkdir('/opt/walter-raw-vault')
        self.assertEqual(self.root('memory'), '/walter/memory')
        self.assertEqual(self.root('raw-vault'), '/opt/walter-raw-vault')

    def test_symlinked_target_is_not_taken_for_a_moved_module(self):
        self.mkdir('/opt/walter-memory')
        self.mkdir('/walter')
        (self.fs / 'walter/memory').symlink_to(self.fs / 'opt/walter-memory')
        self.assertEqual(self.root('memory'), '/opt/walter-memory')

    def test_walter_root_override_and_validation(self):
        with mock.patch.dict(os.environ, {'WALTER_ROOT': '/srv/w'}):
            self.assertEqual(self.root('colab'), '/srv/w/colab')
        for bad in ('relative', '/', '/walter/../etc'):
            with mock.patch.dict(os.environ, {'WALTER_ROOT': bad}):
                with self.assertRaises(ValueError):
                    paths.walter_root()

    def test_module_path_rejects_traversal_and_unknown_modules(self):
        self.assertEqual(str(paths.module_path('colab', 'contracts', 'colab.json', catalog=self.catalog, filesystem=self.fs)),
                         '/walter/colab/contracts/colab.json')
        for part in ('../etc', '/etc/passwd'):
            with self.assertRaises(ValueError):
                paths.module_path('colab', part, catalog=self.catalog, filesystem=self.fs)
        with self.assertRaises(ValueError):
            paths.module_root('nope', catalog=self.catalog, filesystem=self.fs)

    def test_join_keeps_external_paths_and_expands_module_paths(self):
        self.assertEqual(str(paths.join('/walter/memory', '.')), '/walter/memory')
        self.assertEqual(str(paths.join('/walter/memory', 'walter_memory/events.py')), '/walter/memory/walter_memory/events.py')
        self.assertEqual(str(paths.join('/walter/memory', '/root/.pgpass')), '/root/.pgpass')
        with self.assertRaises(ValueError):
            paths.join('/walter/memory', '/opt/../etc')


class RelativeContractTests(unittest.TestCase):
    """Owner manifests are relative; the compiled registry is absolute and follows the module when it moves."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fs = Path(self.temp.name)
        sample = json.loads((Path(__file__).resolve().parents[1] / 'modules/registry.json').read_text())
        self.module = next(m for m in sample['modules'] if m['id'] == 'colab')
        root = Path(self.module['root'])
        def rel(v):
            p = Path(v)
            return '.' if p == root else (str(p.relative_to(root)) if p.is_relative_to(root) else v)
        self.manifest = {k: v for k, v in self.module.items() if k != 'root'}
        self.manifest.update(requires=[], optional=[])  # single-module catalog
        for key in ('anchors', 'backup_paths', 'core_paths'):
            self.manifest[key] = [rel(v) for v in self.module[key]]
        self.manifest['contract'] = dict(self.module['contract'], target_root='colab',
                                         config_paths=[rel(v) for v in self.module['contract']['config_paths']])
        self.catalog = self.fs / 'catalog.json'
        self.catalog.write_text(json.dumps({'schema_version': 1, 'modules': [
            {'id': 'colab', 'target': 'colab', 'legacy': '/opt/walter-colab', 'manifest': 'contracts/colab.json'}]}))
        env = mock.patch.dict(os.environ, {'WALTER_ROOT': '/walter'})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.temp.cleanup()

    def place(self, root):
        target = self.fs / root.lstrip('/') / 'contracts/colab.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contracts.encoded(self.manifest))

    def compiled(self):
        return contracts.compile_registry(self.catalog, root=self.fs)['modules'][0]

    def test_registry_follows_the_module_without_editing_its_contract(self):
        self.place('/opt/walter-colab')
        before = self.compiled()
        self.assertEqual(before['root'], '/opt/walter-colab')
        self.assertIn('/opt/walter-colab/contracts/colab.json', before['anchors'])
        self.assertEqual(before['contract']['target_root'], '/walter/colab')
        (self.fs / 'walter').mkdir()
        (self.fs / 'opt/walter-colab').rename(self.fs / 'walter/colab')
        after = self.compiled()
        self.assertEqual(after['root'], '/walter/colab')
        self.assertIn('/walter/colab/contracts/colab.json', after['anchors'])
        self.assertTrue(all(p.startswith('/walter/colab') for p in after['backup_paths']))

    def test_relative_manifest_expands_to_the_registry_entry(self):
        self.place('/walter/colab')
        self.assertEqual(contracts.expand(self.manifest, '/walter/colab', '/walter/colab'), self.compiled())

    def test_manifest_target_must_match_catalog(self):
        self.manifest['contract']['target_root'] = 'compute/colab'
        self.place('/walter/colab')
        with self.assertRaisesRegex(ValueError, 'target differs'):
            self.compiled()

    def test_traversal_in_relative_manifest_rejected(self):
        self.manifest['backup_paths'].append('../walter-core')
        self.place('/walter/colab')
        with self.assertRaises(ValueError):
            self.compiled()

    def test_compiled_registry_still_requires_absolute_paths(self):
        with self.assertRaises(ValueError):
            contracts.validate(self.manifest)
        contracts.validate(self.manifest, source=True)

    def test_installed_catalog_compiles_to_the_committed_registry(self):
        core = Path(__file__).resolve().parents[1]
        self.assertTrue(contracts.check(core / 'modules/catalog.json')['ok'])


if __name__ == '__main__':
    unittest.main()
