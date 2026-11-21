import sys, json, contextlib, io, os
from pathlib import Path
HERMES_HOME=Path(os.environ.get('HERMES_HOME') or Path.home()/'.hermes')
sys.path.insert(0,str(HERMES_HOME/'hermes-agent'))
from hermes_cli.plugins import PluginManager
from hermes_cli.plugins_manifest import parse_manifest_file
from tools.registry import registry
root=HERMES_HOME/'plugins'/'walter-computer-use'
manifest=parse_manifest_file(root/'plugin.yaml',root,'user','')
manager=PluginManager()
manager._load_plugin(manifest)
loaded=manager._plugins[manifest.name]
entry=registry.get_entry('computer_use',scope=manager.scope_key)
report={'plugin_error': loaded.error or None,'registered':entry is not None,
        'handler_module':getattr(entry.handler,'__module__',None) if entry else None,
        'desktop_contacted':False}
if entry:
    properties=entry.schema['parameters']['properties']
    report['actions']=properties['action']['enum']
    report['walter_policy_loaded']=report['handler_module']=='walter_computer.ports.hermes'
print(json.dumps(report))
manager.unload()
if loaded.error or not report.get('walter_policy_loaded'):
    raise SystemExit(1)
