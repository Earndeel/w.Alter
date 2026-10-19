"""Public CLI contract; uses the real bound notebook, not mocks."""
import json
from pathlib import Path
import subprocess
import sys
def main():
    ROOT=Path('/opt/walter-colab')
    script=ROOT/'run.py'
    assert script.exists(), 'Mount-free public command missing'
    p=subprocess.run([str(ROOT/'mcp/.venv/bin/python'),str(script),'status'],capture_output=True,text=True,timeout=300)
    assert p.returncode==0, p.stderr
    result=json.loads(p.stdout.strip().splitlines()[-1])
    assert result['store']=='/content/walter-cache-store'
    assert result['drive_mounted'] is False
    assert result['google_credentials_present'] is False
    print(json.dumps(result))

if __name__=='__main__':main()
