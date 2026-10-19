import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from walter_platform import interconnect


class InterconnectTests(unittest.TestCase):
    """A module reaches another only through a declared interface, never through its directory."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fs = Path(self.temp.name)
        self.catalog = self.fs / 'catalog.json'
        self.catalog.write_text(json.dumps({'schema_version': 1, 'modules': [
            {'id': 'memory', 'target': 'memory', 'legacy': '/opt/walter-memory', 'manifest': 'contracts/memory.json'},
            {'id': 'bus', 'target': 'memory', 'legacy': '/opt/walter-memory', 'manifest': 'contracts/bus.json'},
            {'id': 'raw-vault', 'target': 'memory/vault', 'legacy': '/opt/walter-raw-vault', 'manifest': 'contracts/raw-vault.json'},
            {'id': 'router', 'target': 'router', 'legacy': '/opt/walter-router', 'manifest': 'contracts/router.json'},
        ]}))
        for root in ('opt/walter-memory', 'opt/walter-raw-vault', 'opt/walter-router'):
            (self.fs / root).mkdir(parents=True)
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
        return interconnect.scan(catalog=self.catalog, filesystem=self.fs)

    def test_clean_modules_pass(self):
        self.write('opt/walter-memory/walter_memory/llm.py', 'subprocess.run(["walter-router", "pick", task])\n')
        self.assertTrue(self.scan()['ok'])

    def test_path_to_another_module_is_a_violation(self):
        self.write('opt/walter-memory/walter_memory/llm.py', 'sys.path.append("/opt/walter-router")\n')
        result = self.scan()
        self.assertFalse(result['ok'])
        self.assertEqual(result['pairs'], ['bus+memory -> router'])
        self.assertEqual(result['violations'][0]['line'], 1)

    def test_target_layout_paths_are_recognised_and_nested_targets_kept_apart(self):
        self.write('opt/walter-router/walter_router/x.py', 'MODELS = "/walter/memory/vault/objects"\n')
        self.assertEqual(self.scan()['pairs'], ['router -> raw-vault'])

    def test_modules_sharing_a_root_form_one_home(self):
        self.write('opt/walter-memory/walter_memory/bus.py', 'ROOT = "/opt/walter-memory"\n')
        self.assertTrue(self.scan()['ok'])

    def test_docs_tests_and_environments_are_not_interfaces(self):
        for path in ('opt/walter-memory/docs/a.md', 'opt/walter-memory/tests/test_x.py',
                     'opt/walter-memory/venv/lib/x.py', 'opt/walter-memory/README.md'):
            self.write(path, '/opt/walter-router/bin/walter-router\n')
        self.assertTrue(self.scan()['ok'])

    def test_installed_walter_is_clean(self):
        self.assertEqual(interconnect.scan()['violations'], [])


if __name__ == '__main__':
    unittest.main()
