import asyncio,importlib.abc,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'runtime')]
from walter_browse import facade

class BoundaryTests(unittest.TestCase):
 def test_import_without_hermes_and_shared_state(self):
  script='''import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in ('hermes_constants','hermes_cli','agent','tools','run_agent'): raise AssertionError(name)
sys.meta_path.insert(0,Block())
import walter_browse,universal_router,browse_session,profile_index,result_cache,search_lite
print('ok')
'''
  env={**os.environ,'PYTHONPATH':os.pathsep.join([str(ROOT),str(ROOT/'runtime')]),'HERMES_HOME':'/absent-hermes'}
  p=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=15)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_validation_is_shared_and_blocks_private_targets(self):
  for target in ('http://127.0.0.1/','http://localhost/','file:///etc/passwd'):
   with self.assertRaises(ValueError):facade._validate_request({'url':target,'content_only':True})
  with self.assertRaises(ValueError):facade._validate_request({'query':'x','url':'https://x.test/'})
 def test_errors_do_not_disclose_subprocess_diagnostics(self):
  req=facade._validate_request({'query':'fixture'})
  with patch.object(facade,'_resolve_router_command',return_value=['fake']),patch.object(facade.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','password=fixture-sensitive')):
   self.assertNotIn('fixture-sensitive',json.dumps(facade._run_router(req)))
 def test_hermes_port_registers_shared_handler(self):
  spec=importlib.util.spec_from_file_location('browse_port',ROOT/'ports/hermes/__init__.py');port=importlib.util.module_from_spec(spec);spec.loader.exec_module(port)
  class Ctx:
   def register_tool(self,**kwargs):self.data=kwargs
  ctx=Ctx();port.register(ctx);self.assertIs(ctx.data['handler'],facade.browse)
 def test_runtime_path_does_not_follow_harness_home(self):
  from walter_paths import state_home
  with patch.dict(os.environ,{'HERMES_HOME':'/other','WALTER_BROWSE_STATE_DIR':'/shared-fixture'}):
   self.assertEqual(state_home(),Path('/shared-fixture'))

if __name__=='__main__':unittest.main()
