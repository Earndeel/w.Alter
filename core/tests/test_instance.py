import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from walter_platform import instance, neutrality

MANIFEST = '''schema_version = 1
id = "demo"
[owner]
address = "Madame"
name = "Alice Exemple"
emails = ["alice@example.org"]
language = "en"
[privacy]
markers = ["exemple-corp"]
'''


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / 'instances' / 'demo'
        self.base.mkdir(parents=True)
        (self.base / 'instance.toml').write_text(MANIFEST)
        env = mock.patch.dict(os.environ, {'WALTER_INSTANCE': str(self.base), 'WALTER_ROOT': '/walter'})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_resolution_order_env_then_pointer_then_default(self):
        self.assertEqual(instance.root(), self.base)
        pointer = Path(self.temp.name) / 'pointer'
        pointer.write_text('/instances/other\n')
        with mock.patch.dict(os.environ, {'WALTER_INSTANCE': ''}):
            self.assertEqual(instance.root(pointer=pointer), Path('/instances/other'))
            self.assertEqual(instance.root(pointer=Path(self.temp.name) / 'absent'), Path('/instance'))
        with mock.patch.dict(os.environ, {'WALTER_INSTANCE': 'relative/path'}):
            with self.assertRaises(ValueError):
                instance.root()

    def test_manifest_owner_and_render(self):
        self.assertEqual(instance.owner()['address'], 'Madame')
        self.assertEqual(instance.owner()['timezone'], 'UTC')
        self.assertEqual(instance.render('Bonjour {{owner.address}} ({{instance.id}})'), 'Bonjour Madame (demo)')
        with self.assertRaises(ValueError):
            instance.render('{{owner.unknown}}')

    def test_invalid_manifests_are_refused(self):
        (self.base / 'instance.toml').write_text('schema_version = 1\nid = "Bad Id"\n[owner]\naddress = "x"\n')
        with self.assertRaises(ValueError):
            instance.manifest()
        (self.base / 'instance.toml').write_text('schema_version = 1\nid = "demo"\n')
        with self.assertRaises(ValueError):
            instance.manifest()

    def test_paths_stay_inside_the_instance(self):
        self.assertEqual(instance.state('skills', 'reports'), self.base / 'state' / 'skills' / 'reports')
        with self.assertRaises(ValueError):
            instance.path('../escape')
        with self.assertRaises(ValueError):
            instance.path('/etc/passwd')

    def test_config_override_wins_over_module_default(self):
        fs = Path(self.temp.name) / 'fs'
        (fs / 'walter' / 'router' / 'config').mkdir(parents=True)
        (fs / 'walter' / 'router' / 'config' / 'subscriptions.json').write_text('{}')
        catalog = Path(self.temp.name) / 'catalog.json'
        catalog.write_text(json.dumps({'schema_version': 1, 'modules': [
            {'id': 'router', 'target': 'router', 'legacy': None, 'manifest': 'contracts/router.json'}]}))
        found = instance.config('router', 'subscriptions.json', catalog=catalog, filesystem=fs)
        self.assertEqual(str(found), '/walter/router/config/subscriptions.json')
        (self.base / 'config' / 'router').mkdir(parents=True)
        (self.base / 'config' / 'router' / 'subscriptions.json').write_text('{"mine": 1}')
        self.assertEqual(instance.config('router', 'subscriptions.json', catalog=catalog, filesystem=fs),
                         self.base / 'config' / 'router' / 'subscriptions.json')

    def test_check_reports_layout_bootstrap_and_secret_values(self):
        out = instance.check()
        self.assertFalse(out['ok'])
        self.assertTrue(any('missing directories' in p for p in out['problems']))
        for d in instance.LAYOUT:
            (self.base / d).mkdir()
        (self.base / 'bootstrap').chmod(0o755)
        self.assertIn('bootstrap/ must be private (0700)', instance.check()['problems'])
        (self.base / 'bootstrap').chmod(0o700)
        self.assertTrue(instance.check()['ok'], instance.check())
        (self.base / 'instance.toml').write_text(MANIFEST + '[accounts.telegram]\nbot_token = "x"\ntoken_ref = "vault:item"\n')
        problems = instance.check()['problems']
        self.assertEqual(len(problems), 1)
        self.assertIn('accounts.telegram.bot_token', problems[0])

    def test_contract_paths_designate_the_active_instance(self):
        from walter_platform import contracts, paths
        self.assertEqual(str(paths.join('/walter/soul', '@instance/soul')), str(self.base / 'soul'))
        self.assertEqual(str(paths.join('/walter/core', '@instance')), str(self.base))
        self.assertEqual(str(contracts.contract_path('@instance/config')), str(self.base / 'config'))
        with self.assertRaises(ValueError):
            paths.join('/walter/soul', '@instance/../etc')
        self.assertFalse(paths.is_instance_path('@instances'))

    def test_markers_come_from_the_instance(self):
        self.assertEqual(instance.markers(), ['Alice Exemple', 'alice@example.org', 'exemple-corp', 'Madame'])


class NeutralityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fs = Path(self.temp.name)
        self.catalog = self.fs / 'catalog.json'
        self.catalog.write_text(json.dumps({'schema_version': 1, 'modules': [
            {'id': 'soul', 'target': 'soul', 'legacy': None, 'manifest': 'contracts/soul.json', 'neutral': True},
            {'id': 'router', 'target': 'router', 'legacy': None, 'manifest': 'contracts/router.json'},
        ]}))
        env = mock.patch.dict(os.environ, {'WALTER_ROOT': '/walter'})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, text):
        p = self.fs / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def scan(self):
        return neutrality.scan(catalog=self.catalog, filesystem=self.fs, markers=['Madame', 'alice@example.org'])

    def test_clean_modules_pass(self):
        self.write('walter/soul/bin/walter-soul', 'print("{{owner.address}}")\n')
        self.write('walter/router/README.md', 'neutral text, /rooted is not /root\n')
        out = self.scan()
        self.assertTrue(out['ok'], out)

    def test_neutral_module_fails_on_marker_or_host_home(self):
        self.write('walter/soul/identity.md', 'Tu sers madame.\n')
        self.write('walter/soul/bin/x.py', "HOME = '/root/.hermes'\n")
        out = self.scan()
        self.assertFalse(out['ok'])
        soul = next(m for m in out['modules'] if m['module'] == 'soul')
        self.assertEqual(soul['files'], ['/walter/soul/bin/x.py', '/walter/soul/identity.md'])

    def test_other_modules_are_counted_not_failed(self):
        self.write('walter/router/alerts.py', 'send("Madame, alice@example.org")\n')
        out = self.scan()
        self.assertTrue(out['ok'])
        router = next(m for m in out['modules'] if m['module'] == 'router')
        self.assertEqual((router['private_marker_files'], router['host_home_files']), (1, 0))
        self.assertNotIn('files', router)

    def test_instance_content_is_not_scanned(self):
        self.write('walter/soul/build/agent.md', 'Madame\n')
        self.write('walter/soul/skills/x/SKILL.md', '/root\n')
        self.assertTrue(self.scan()['ok'])


if __name__ == '__main__':
    unittest.main()
