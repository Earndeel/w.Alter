"""Standalone CLI regression: do not let PYTHONPATH/shared runtime hide missing package bootstrap."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_empty_fixture_scenario_runs_without_an_inherited_core_import_path(tmp_path):
    script=Path(__file__).resolve().parents[1]/'bin/walter-scenario'
    fixture=tmp_path/'bootstrap.yaml'
    fixture.write_text('name: bootstrap-fixture\nsteps: []\nassertions: []\n')
    code='''import runpy,sys
from pathlib import Path
sys.path[:]=[p for p in sys.path if not (Path(p)/"walter_platform").is_dir()]
sys.argv=[sys.argv[1],"run",sys.argv[2],"--json"]
runpy.run_path(sys.argv[0],run_name="__main__")
'''
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    env.update(WALTER_INSTANCE=str(tmp_path/'instance'),PYTHONDONTWRITEBYTECODE='1')
    proc=subprocess.run([sys.executable,'-I','-c',code,str(script),str(fixture)],env=env,
                        capture_output=True,text=True,timeout=30)
    assert proc.stdout.strip(),proc.stderr
    report=json.loads(proc.stdout)
    assert proc.returncode==1 and report['scenario']=='bootstrap-fixture' and report['ok'] is False
    assert 'ModuleNotFoundError' not in proc.stderr
