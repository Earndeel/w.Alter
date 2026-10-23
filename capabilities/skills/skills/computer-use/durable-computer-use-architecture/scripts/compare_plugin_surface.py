#!/usr/bin/env python3
"""Compare two Computer Use plugins under one certified Hermes runtime.

Usage:
  python3 scripts/compare_plugin_surface.py \
    --release /path/to/certified/hermes \
    --baseline /path/to/deployed/plugin \
    --candidate /path/to/candidate/plugin \
    --output /tmp/surface.json

No driver is started and no device is touched.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, tempfile
from pathlib import Path

PROBE = r'''
import hashlib,json
from hermes_cli.plugins import discover_plugins,get_plugin_manager
from tools.computer_use.backend import registered_action_extensions,registered_backend_names
from tools.computer_use.schema import COMPUTER_USE_SCHEMA
from tools.computer_use.tool import _computer_use_schema_overrides
discover_plugins(force=True)
r=next(x for x in get_plugin_manager().list_plugins() if x.get("name")=="walter-computer-use")
o=_computer_use_schema_overrides(); p=((o.get("parameters") or {}).get("properties") or {})
enc=lambda x: json.dumps(x,sort_keys=True,separators=(",",":")).encode()
print(json.dumps({
 "plugin_version":r.get("version"),"tool_name":COMPUTER_USE_SCHEMA.get("name"),
 "raw_schema_sha256":hashlib.sha256(enc(COMPUTER_USE_SCHEMA)).hexdigest(),
 "override_sha256":hashlib.sha256(enc(o)).hexdigest(),
 "registered_backends":list(registered_backend_names()),
 "registered_actions":[x.name for x in registered_action_extensions()],
 "action_enum":((p.get("action") or {}).get("enum") or []),"goal_property":p.get("goal")
},sort_keys=True))
'''

def probe(release: Path, plugin: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="cu-surface-") as raw:
        home=Path(raw); dst=home/"plugins"/"walter-computer-use"; dst.parent.mkdir(parents=True)
        shutil.copytree(plugin,dst,ignore=shutil.ignore_patterns("__pycache__","*.pyc","*.pyo"))
        (home/"config.yaml").write_text("plugins:\n  enabled:\n    - walter-computer-use\ncomputer_use:\n  backend: walter\n")
        env={**os.environ,"HERMES_HOME":raw,"PYTHONPATH":str(release),"PYTHONDONTWRITEBYTECODE":"1"}
        out=subprocess.check_output([str(release/"venv/bin/python"),"-c",PROBE],env=env,text=True)
        return json.loads(out.strip().splitlines()[-1])

def main():
    ap=argparse.ArgumentParser()
    for key in ("release","baseline","candidate","output"): ap.add_argument(f"--{key}",type=Path,required=True)
    a=ap.parse_args(); results={"baseline":probe(a.release,a.baseline),"candidate":probe(a.release,a.candidate)}
    clean=lambda x:{k:v for k,v in x.items() if k!="plugin_version"}
    report={"runtime_release":str(a.release),"surfaces_equal":clean(results["baseline"])==clean(results["candidate"]),"results":results}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"output":str(a.output),"surfaces_equal":report["surfaces_equal"]}))
    raise SystemExit(0 if report["surfaces_equal"] else 1)
if __name__=="__main__": main()
