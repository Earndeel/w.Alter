"""Real bootstrap contract: staged, hash-pinned code loads without Drive mount."""
import json
from pathlib import Path
import subprocess
def main():
    root=Path('/walter/capabilities/colab')
    p=subprocess.run([str(root/'mcp/.venv/bin/python'),str(root/'run.py'),'bootstrap'],capture_output=True,text=True,timeout=300)
    assert p.returncode==0,p.stderr
    r=json.loads(p.stdout.strip().splitlines()[-1])
    assert r['bootstrap']['store']=='/content/walter-cache-store'
    assert r['runtime']['drive_mounted'] is False
    assert r['bootstrap']['cache_module_imported'] is True
    assert r['bootstrap']['original_sha256']=='28f153ef9ffd9b61a3e0049fc15f112054d2b405891a5513ebf4dacb2b1d278b'
    assert r['bootstrap']['dependency_cache_archive_present'] is False
    print(json.dumps(r))

if __name__=='__main__':main()
