"""REAL Drive -> Colab -> Drive proof, private files only, credentials VM-side."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/opt/walter-colab')
import transfer
assert hasattr(transfer,'DriveStore'), 'Drive-side transport missing'
ROOT=Path('/root/.hermes/cache/scratch/colab-no-mount')
# Test bytes already exercised against the real runtime; not synthetic API output.
src=ROOT/'walter-transport-binary-test.bin'
store=transfer.DriveStore('1FkpPcvrgKTS0rMs7qtd0txZ1tK7mfbx9')
first=store.save(src)
print(json.dumps({'stage':'DRIVE_PRIVATE_SAVE_READBACK',**first}),flush=True)
local=ROOT/'walter-transport-from-drive.bin'
if local.exists():local.unlink()
got=store.fetch(first['name'],local)
b=transfer.Browser('colab-qwen-cache','1A3OT3nVrrvfOyZs3maCWQxou4_QrCPWf')
# Preserve original leaf name: browser uploads use leaf names as explicit targets.
up=ROOT/'roundtrip'/first['name']
up.parent.mkdir(exist_ok=True)
if up.exists():up.unlink()
local.rename(up)
b.upload(up)
back=ROOT/'return'/first['name']
back.parent.mkdir(exist_ok=True)
if back.exists():back.unlink()
readback=b.download(first['name'],back,expected_sha256=first['sha256'])
second=store.save(back)
assert second['id']==first['id'], 'Idempotent save created an unexpected duplicate'
assert first['sha256']==readback['sha256']==second['sha256']
report={'drive_to_colab_to_drive_verified':True,'private':first['private'],'idempotent_same_id':True,'sha256':first['sha256'],'size_bytes':first['size_bytes'],'drive_file_id':first['id'],'drive_folder_id':store.folder,'google_credentials_in_colab':False,'runtime_readback':readback}
(ROOT/'drive-roundtrip.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
