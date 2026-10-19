import copy
import json
import tempfile
import unittest
from pathlib import Path

from walter_platform import contracts, registry


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        sample = json.loads((Path(__file__).resolve().parents[1] / 'modules/registry.json').read_text())
        self.modules = sample['modules']
        self.catalog = self.root / 'catalog.json'
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        entries = []
        for module in self.modules:
            path = Path(module['root']) / 'contracts' / (module['id'] + '.json')
            target = self.root / str(path).lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contracts.encoded(module))
            entries.append({'id': module['id'], 'manifest': str(path)})
        self.catalog.write_bytes(contracts.encoded({'schema_version': 1, 'modules': entries}))

    def compile(self):
        return contracts.compile_registry(self.catalog, root=self.root)

    def test_compiler_is_deterministic_and_export_drift_fails(self):
        result = self.compile()
        compiled = self.root / 'registry.json'
        compiled.write_bytes(contracts.encoded(result))
        self.assertTrue(contracts.check(self.catalog, root=self.root)['ok'])
        self.modules[0]['backup_paths'].append('/new-required-state')
        self.write()
        self.assertFalse(contracts.check(self.catalog, root=self.root)['ok'])
        self.assertEqual(result['modules'], sorted(result['modules'], key=lambda m: m['id']))

    def test_duplicate_resource_owner_is_rejected(self):
        resource = copy.deepcopy(self.modules[0]['contract']['resources'][0])
        resource['owner'] = self.modules[1]['id']
        self.modules[1]['contract']['resources'].append(resource)
        self.write()
        with self.assertRaisesRegex(ValueError, 'multiple owners'):
            self.compile()

    def test_consumer_cannot_claim_wrong_owner(self):
        self.modules[0]['contract']['resources'].append({'id': 'identity-sources', 'role': 'consumer',
                                                       'owner': 'core', 'durability': 'canonical'})
        self.write()
        with self.assertRaisesRegex(ValueError, 'matching owner'):
            self.compile()

    def test_mandatory_cycle_rejected_optional_cycle_allowed(self):
        one, two = self.modules[0], self.modules[1]
        one['optional'] = [two['id']]; two['optional'] = [one['id']]
        one['requires'] = []; two['requires'] = []
        self.write(); self.compile()
        one['requires'] = one.pop('optional'); one['optional'] = []
        two['requires'] = two.pop('optional'); two['optional'] = []
        self.write()
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.compile()

    def test_path_traversal_and_escape_from_fixture_are_rejected(self):
        self.modules[0]['backup_paths'].append('/opt/../etc')
        self.write()
        with self.assertRaises(ValueError):
            self.compile()

    def test_invalid_operational_contract_rejected(self):
        for invalid in (0, -1, float('inf'), True):
            m = copy.deepcopy(self.modules[0])
            m['contract']['operations'][0]['timeout_seconds'] = invalid
            with self.assertRaises(ValueError):
                contracts.validate(m)

    def test_generated_registry_survives_optional_module_removal(self):
        compiled = self.root / 'registry.json'
        compiled.write_bytes(contracts.encoded(self.compile()))
        manifest = self.root / str(Path(self.modules[0]['root']) / 'contracts' / (self.modules[0]['id'] + '.json')).lstrip('/')
        manifest.unlink()
        # Runtime discovery uses the generated cache, independent of optional module imports/files.
        self.assertEqual(len(registry.load(compiled)['modules']), len(self.modules))
        with self.assertRaises(FileNotFoundError):
            self.compile()

    def test_documentation_is_derived_without_health_claim(self):
        text = contracts.render_markdown(self.compile())
        self.assertIn('leur réussite est mesurée séparément', text)
        self.assertIn('## memory', text)


if __name__ == '__main__':
    unittest.main()
