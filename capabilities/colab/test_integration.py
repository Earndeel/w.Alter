"""Integration test against the REAL bound CPU Colab notebook, not mocked output."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,'/walter/capabilities/colab')
import transfer
ROOT=Path('/root/.hermes/cache/scratch/colab-no-mount')
ROOT.mkdir(parents=True,exist_ok=True)
assert hasattr(transfer,'Browser'), 'Browser transfer implementation missing'
b=transfer.Browser('colab-qwen-cache','1A3OT3nVrrvfOyZs3maCWQxou4_QrCPWf')
p=ROOT/'walter-transport-binary-test.bin'
if not p.exists():p.write_bytes(os.urandom(8*1024*1024+37))
sha=transfer.sha256_file(p)
started=time.perf_counter()
receipt=b.upload(p)
print(json.dumps({'stage':'UPLOADED_REAL_BROWSER','receipt':receipt}),flush=True)
assert receipt['size_bytes']==p.stat().st_size
q=ROOT/'walter-transport-binary-readback.bin'
if q.exists():q.unlink()
receipt=b.download(p.name,q,expected_sha256=sha)
assert transfer.sha256_file(q)==sha
report={'source_size_bytes':p.stat().st_size,'sha256':sha,'receipt':receipt,'elapsed_seconds':round(time.perf_counter()-started,3),'google_credentials_injected':False,'public_endpoint_created':False,'gpu_allocated':False}
(ROOT/'transport-integration.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
