#!/walter/capabilities/colab/mcp/.venv/bin/python
"""Low-level bound notebook cache transport without Drive mounts.

status       read runtime toolbar/resources only; never initializes or allocates
put PATH     save an immutable private Drive cache object with independent readback
stage NAME   private Drive -> browser Files -> /content/walter-cache-store
persist NAME runtime checksum/size -> browser Files -> verified private Drive

bootstrap/stage/persist may initialize the selected runtime when disconnected.
These low-level commands DO NOT automatically release it afterward; use bounded
on-demand orchestration for lifecycle/cleanup, not a permanent GPU worker.
No shell, no public file server, no OAuth credentials on the Colab runtime.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from bridge import Bridge
from drive_store import DriveStore
from transfer import Browser, STORE, safe_filename, sha256_file

ROOT=Path(__file__).parent
SCRATCH=Path.home()/'.hermes/cache/scratch/colab-no-mount'

def report_from_output(text, prefix):
    values=[line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    if len(values)!=1:raise RuntimeError('Missing or ambiguous runtime verification marker')
    return json.loads(values[0])

def runtime_hash_code(name, *, allow_missing=False):
    return '''from pathlib import Path
import hashlib,json
store=Path('''+repr(STORE)+''')
if store.is_symlink() or any(p.is_symlink() for p in store.parents):
    raise ValueError('Runtime cache store or parent is a symlink')
if not store.is_dir():raise ValueError('Runtime cache store must already be a directory')
p=store/'''+repr(safe_filename(name))+'''
if p.is_symlink():raise ValueError('Runtime cache object is a symlink')
if not p.exists() and '''+repr(allow_missing)+''':
    result={'name':p.name,'exists':False}
else:
    if not p.is_file():raise ValueError('Runtime cache object is not a regular file')
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    result={'name':p.name,'exists':True,'size_bytes':p.stat().st_size,'sha256':h.hexdigest()}
print('WALTER_FILE='+json.dumps(result))
'''

def bootstrap_code():
    expected={name:sha256_file(ROOT/name) for name in ['cache_runtime.py','walter-qwen-inference.py']}
    return '''from pathlib import Path
import hashlib,importlib.util,json,os,shutil
os.environ['WALTER_COLAB_CACHE_DIR']='/content/walter-cache-store'
expected='''+repr(expected)+'''
for name,digest in expected.items():
    src=Path('/content/walter-cache-store')/name
    dst=Path('/content')/name
    assert src.is_file() and not src.is_symlink()
    assert hashlib.sha256(src.read_bytes()).hexdigest()==digest
    assert not dst.is_symlink()
    if dst.exists():assert hashlib.sha256(dst.read_bytes()).hexdigest()==digest
    else:shutil.copy2(src,dst)
spec=importlib.util.spec_from_file_location('walter_mount_free_cache','/content/cache_runtime.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
store=m.require_store()
assert store==Path('/content/walter-cache-store')
print('WALTER_BOOTSTRAP='+json.dumps({'store':str(store),'cache_module_imported':True,'original_sha256':expected['walter-qwen-inference.py'],'dependency_cache_archive_present':(store/m.ARCHIVE_NAME).exists(),'google_credentials_injected':False}))
'''

async def execute(args):
    config=json.loads((ROOT/'config.json').read_text())
    if config['new_purchase_allowed'] or config['google_credentials_in_runtime_allowed']:
        raise ValueError('Unexpected widening of the fixed cache security contract')
    if args.command=='put':return DriveStore(config['drive_folder_id']).save(args.path)
    browser=Browser(config['browser_session'],config['notebook_id'])
    bridge=Bridge(browser)
    if args.command=='status':
        return {'runtime':bridge.runtime_state(),'resources':bridge.resources(),'allocation_requested':False}
    store=DriveStore(config['drive_folder_id'])
    SCRATCH.mkdir(parents=True,exist_ok=True)
    async with bridge.connect():
        state=await bridge.initialize()
        if state['drive_mounted'] or state['google_credentials_present']:
            raise RuntimeError('Mount-free isolation proof failed')
        if args.command=='bootstrap':
            code=bootstrap_code()
            cell=await bridge.set_code('walter-cache-bootstrap',code)
            result=report_from_output(await bridge.run(cell),'WALTER_BOOTSTRAP=')
            return {'runtime':state,'bootstrap':result}
        name=safe_filename(args.name)
        with tempfile.TemporaryDirectory(prefix='command-',dir=SCRATCH) as temporary:
            path=Path(temporary)/name
            if args.command=='stage':
                expected=store.fetch(name,path)
                before=report_from_output(await bridge.code(runtime_hash_code(name,allow_missing=True)),'WALTER_FILE=')
                if before['exists'] and (before['sha256']!=expected['sha256'] or before['size_bytes']!=expected['size_bytes']):
                    raise ValueError('Immutable runtime cache name collision; choose an explicit new version')
                if before['exists']:
                    sent={'seconds':0}
                    actual=before
                else:
                    sent=browser.upload(path)
                    actual=report_from_output(await bridge.code(runtime_hash_code(name)),'WALTER_FILE=')
                if actual['sha256']!=expected['sha256'] or actual['size_bytes']!=expected['size_bytes']:
                    raise RuntimeError('Colab readback differs from the exact private Drive object')
                return {'stage':'drive-to-colab','runtime':state,'drive':expected,'runtime_readback':actual,
                        'transport_seconds':sent['seconds'],'upload_skipped':before['exists'],
                        'google_credentials_in_colab':False}
            actual=report_from_output(await bridge.code(runtime_hash_code(name)),'WALTER_FILE=')
            downloaded=browser.download(name,path,expected_sha256=actual['sha256'],
                                        expected_size_bytes=actual['size_bytes'])
            saved=store.save(path)
            if saved['sha256']!=downloaded['sha256']:raise RuntimeError('Persisted cache readback mismatch')
            return {'stage':'colab-to-drive','runtime':state,'drive':saved,'runtime_readback':downloaded,
                    'google_credentials_in_colab':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status',help='Read runtime/resources only; no initialization or allocation')
    sub.add_parser('bootstrap',help='Low-level runtime operation; may allocate; no automatic cleanup')
    put=sub.add_parser('put');put.add_argument('path',type=Path)
    for command in ['stage','persist']:
        p=sub.add_parser(command,help='Low-level runtime operation; may allocate; no automatic cleanup');p.add_argument('name')
    args=parser.parse_args()
    try:
        result=asyncio.run(execute(args))
    except Exception as error:
        # Third-party exceptions can contain signed URLs. Never emit their raw text.
        print(json.dumps({'status':'failed','error_type':type(error).__name__,
                          'detail':'Inspect bound notebook and protected VM diagnostics; no fallback or credential export.'}),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
