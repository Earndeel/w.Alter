import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from walter_platform import registry,harness

class RegistryTests(unittest.TestCase):
 def test_cycles_and_unknown_dependencies_fail(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'r.json'
   for modules in [[{'id':'a','requires':['x']}],[{'id':'a','requires':['b']},{'id':'b','requires':['a']}]]:
    p.write_text(json.dumps({'version':1,'modules':modules}))
    with self.assertRaises(ValueError):registry.load(p)
 def test_detects_optional_hermes_import_as_dependency(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'core.py';p.write_text('try:\n from agent.foo import Foo\nexcept ImportError:\n pass\n')
   self.assertEqual(registry.boundary_imports(p)[0]['import'],'agent.foo')
 def test_optional_module_missing_is_data_not_import_failure(self):
  row=registry.inspect_module({'id':'optional','anchors':['/no-such-walter-module']})
  self.assertFalse(row['installed']);self.assertEqual(row['runtime_health'],'not_probed')
 def test_registry_backup_paths_are_absolute(self):
  data=registry.load();self.assertGreater(len(data['modules']),12)
  self.assertTrue(all(Path(x).is_absolute() for x in registry.backup_paths()))

class AttachTests(unittest.TestCase):
 def test_codex_preserves_native_and_idempotent_and_symlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'codex';home.mkdir();real=root/'original.toml'
   original='model = "native-test"\nnotify=["custom-hook"]\n[mcp_servers.other]\ncommand="other"\n'
   real.write_text(original);(home/'config.toml').symlink_to(real)
   preview=harness.attach('codex',home);self.assertTrue(preview['changed']);self.assertEqual(real.read_text(),original)
   result=harness.attach('codex',home,apply=True,backup_root=root/'backup')
   self.assertTrue((home/'config.toml').is_symlink());self.assertIn(original,real.read_text())
   self.assertEqual((Path(result['backup'])/'config.before').read_text(),original)
   self.assertTrue(harness.check('codex',home)['common_mcp'])
   self.assertFalse(harness.attach('codex',home,apply=True)['changed'])
 def test_conflicting_server_is_never_overwritten(self):
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp);p=home/'config.toml';p.write_text('[mcp_servers.walter]\ncommand="custom"\n')
   before=p.read_bytes()
   with self.assertRaises(ValueError):harness.attach('codex',home,apply=True)
   self.assertEqual(before,p.read_bytes())
 def test_claude_keeps_permissions_and_unrelated_server(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);home=root/'.claude';home.mkdir();p=root/'.claude.json'
   p.write_text(json.dumps({'permissions':{'allow':['Read']},'mcpServers':{'other':{'command':'other'}}}))
   harness.attach('claude-code',home,apply=True,backup_root=root/'backups')
   data=json.loads(p.read_text());self.assertEqual(data['permissions'],{'allow':['Read']})
   self.assertIn('other',data['mcpServers']);self.assertTrue(harness.check('claude-code',home)['common_mcp'])
 def test_dsh_preserves_original_patch_and_does_not_claim_context(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'cordis.patch.yml';original='# keep\n- id: custom\n  config: {value: 42}\n';p.write_text(original)
   harness.attach('dsh',root,apply=True,backup_root=root/'backups')
   self.assertTrue(p.read_text().startswith(original));self.assertTrue(harness.check('dsh',root)['common_mcp'])
   self.assertFalse(harness.check('dsh',root)['bindings']['context_plugin'])
 def test_hermes_refuses_duplicate_mcp_surface(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(ValueError):harness.attach('hermes',Path(tmp),apply=True)

if __name__=='__main__':unittest.main()
