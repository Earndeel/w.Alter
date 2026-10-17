import importlib.util,json,pathlib,pytest
from walter_memory import backup_bundle as B

def test_declared_modules_and_outside_dependencies_are_required(tmp_path):
 p=tmp_path/'opt/walter-core/modules/registry.json';p.parent.mkdir(parents=True)
 p.write_text(json.dumps({'version':1,'modules':[{'id':'computer','backup_paths':['/root/device-source','/root/.config/Bitwarden CLI/data.json'],'anchors':['/opt/module/core.py']}]}))
 assert B.module_backup_paths(tmp_path)==['opt/module/core.py','root/.config/Bitwarden CLI/data.json','root/device-source']

def test_bad_registry_path_refused(tmp_path):
 p=tmp_path/'opt/walter-core/modules/registry.json';p.parent.mkdir(parents=True)
 for value in ['relative/path','/tmp/../secret']:
  p.write_text(json.dumps({'version':1,'modules':[{'backup_paths':[value]}]}))
  with pytest.raises(RuntimeError,match='unsafe'):B.module_backup_paths(tmp_path)
