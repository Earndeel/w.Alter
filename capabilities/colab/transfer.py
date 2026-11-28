"""Mount-free Colab file transport. Drive auth is exclusively on this VM."""
from pathlib import Path
import hashlib
import re
import base64
import json
import time
import urllib.request

CHUNK = 1024 * 1024
MAX_BYTES = 1024 ** 3

def iter_chunks(path, size=CHUNK):
    if not isinstance(size, int) or not 1 <= size <= 4 * CHUNK:
        raise ValueError('Invalid bounded chunk size')
    with Path(path).open('rb') as handle:
        yield from iter(lambda: handle.read(size), b'')

def sha256_file(path):
    digest = hashlib.sha256()
    for chunk in iter_chunks(path):
        digest.update(chunk)
    return digest.hexdigest()

STORE = '/content/walter-cache-store'

def __getattr__(name):
    if name == 'DriveStore':
        from drive_store import DriveStore
        return DriveStore
    raise AttributeError(name)

def check_target(info, file_id):
    if (info.get('origin') != 'https://colab.research.google.com'
            or info.get('path') != '/drive/' + file_id):
        raise ValueError('Refusing transfer outside the explicitly bound Colab notebook')


def safe_filename(name):
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}', name)
            or re.search(r'(?:secret|credential|token|api[-_]?key)', name, re.IGNORECASE)):
        raise ValueError('Only a non-secret simple file name is permitted')
    return name


class Browser:
    """Reuse Colab's interactive Files UI transport; never export its auth state.

    This adapter is version-sensitive. Fail closed if Colab changes its Files
    interface. Chunks cross only the localhost browser harness; no public relay.
    """
    def __init__(self, session, notebook_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', session):
            raise ValueError('Invalid browser session identifier')
        self.session, self.notebook_id = session, notebook_id
        self.tab = (Path.home()/'.cache/walter-browser'/f'{session}.tab').read_text().strip()
        self.assert_target()

    def action(self, route, **args):
        if route!='/tab/evaluate':
            self.assert_target()
        req = urllib.request.Request('http://127.0.0.1:9377'+route,
            data=json.dumps({'userId':self.session,'tabId':self.tab,**args}).encode(),
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise RuntimeError('Browser action failed; no credential-bearing error payload logged')
        return result

    def evaluate(self, expression):
        # Recheck in the SAME JS evaluation as every mutation/read/cleanup.
        # A separate location query leaves a navigation race between requests.
        target='/drive/'+self.notebook_id
        bound="(()=>{if(location.origin!=='https://colab.research.google.com'||location.pathname!=="+json.dumps(target)+")throw Error('Bound Colab notebook changed');return ("+expression+")})()"
        return self.action('/tab/evaluate', expression=bound)['result']

    def assert_target(self):
        check_target(self.evaluate('({origin:location.origin,path:location.pathname})'),self.notebook_id)

    def wait_transfer(self, timeout=300):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.assert_target()
            status=self.evaluate('(()=>{const s=window.__walterXfer;return s?{state:s.state,size:s.blob?.size,received:s.received,progress:s.progress}:null})()')
            if status and status['state']=='done':
                return status
            if not status or status['state']=='error':
                raise RuntimeError('Colab Files transfer failed or context lost; no unsafe fallback')
            time.sleep(0.5)
        raise TimeoutError('Bounded Colab Files transfer timeout')

    def upload(self, source):
        source=Path(source)
        name=safe_filename(source.name)
        if source.is_symlink() or not source.is_file():
            raise ValueError('Upload requires a regular unlinked file')
        size=source.stat().st_size
        if not 1<=size<=MAX_BYTES:
            raise ValueError('Upload size outside the conservative limit')
        started=time.perf_counter()
        self.assert_target()
        ready=self.evaluate("(()=>{const n=colab.global.notebook;if(typeof n?.uploadFileToKernel!=='function'||!n.getKernelFiles())return false;if(window.__walterXfer?.state==='working')return false;window.__walterXfer={chunks:[],received:0,state:'staging'};return true})()")
        if not ready:
            raise RuntimeError('Colab Files adapter unavailable or busy')
        try:
            sent=0
            for chunk in iter_chunks(source):
                encoded=base64.b64encode(chunk).decode()
                expected=sent
                sent+=len(chunk)
                got=self.evaluate(f"(()=>{{const s=window.__walterXfer;if(s?.state!=='staging'||s.received!=={expected})throw Error('Transfer state changed');s.chunks.push(Uint8Array.from(atob({json.dumps(encoded)}),c=>c.charCodeAt(0)));s.received+={len(chunk)};return s.received}})()")
                if got!=sent:
                    raise RuntimeError('Browser chunk byte count mismatch')
            if sent!=size:
                raise RuntimeError('Source changed during upload')
            self.evaluate(f"(()=>{{const s=window.__walterXfer;const f=new File(s.chunks,{json.dumps(name)},{{type:'application/octet-stream'}});s.chunks=null;s.state='working';colab.global.notebook.uploadFileToKernel({json.dumps(STORE)},f).then(()=>{{s.state='done'}}).catch(()=>{{s.state='error'}});return true}})()")
            state=self.wait_transfer()
            return {'name':name,'size_bytes':size,'source_sha256':sha256_file(source),
                    'seconds':round(time.perf_counter()-started,3),'transport':'interactive-colab-files-ui'}
        finally:
            self.evaluate("(()=>{if(window.__walterXfer?.state!=='working')delete window.__walterXfer;return true})()")

    def download(self, name, destination, *, expected_sha256, expected_size_bytes=None):
        name=safe_filename(name)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
            raise ValueError('A pinned SHA256 is required before download')
        # Files UI can materialize the whole blob; pin a runtime-measured bound
        # BEFORE contacting the browser, not only after that allocation.
        if type(expected_size_bytes) is not int or not 0<=expected_size_bytes<=MAX_BYTES:
            raise ValueError('A pinned size within the conservative limit is required before download')
        destination=Path(destination)
        if destination.exists() or destination.is_symlink():
            raise ValueError('Never overwrite a local download target')
        destination.parent.mkdir(parents=True,exist_ok=True)
        partial=destination.with_name(destination.name+'.part')
        if partial.exists() or partial.is_symlink():
            raise ValueError('Download staging path already exists')
        self.assert_target()
        started=time.perf_counter()
        ready=self.evaluate(f"(()=>{{const f=colab.global.notebook.getKernelFiles();if(typeof f?.download!=='function'||window.__walterXfer?.state==='working')return false;const s=window.__walterXfer={{state:'working',progress:0}};f.download({json.dumps(STORE+'/'+name)},{{canceled:false,update:p=>{{s.progress=p}}}}).then(b=>{{s.blob=b;s.state='done'}}).catch(()=>{{s.state='error'}});return true}})()")
        if not ready:
            raise RuntimeError('Colab Files download adapter unavailable or busy')
        try:
            state=self.wait_transfer()
            size=state['size']
            if type(size) is not int or not 0<=size<=MAX_BYTES or size!=expected_size_bytes:
                raise RuntimeError('Download byte size differs from the bounded runtime pin')
            digest=hashlib.sha256()
            with partial.open('xb') as handle:
                for offset in range(0,size,CHUNK):
                    stop=min(offset+CHUNK,size)
                    encoded=self.evaluate(f"(async()=>{{const b=window.__walterXfer.blob;const a=new Uint8Array(await b.slice({offset},{stop}).arrayBuffer());let s='';for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode.apply(null,a.subarray(i,i+32768));return btoa(s)}})()")
                    chunk=base64.b64decode(encoded,validate=True)
                    if len(chunk)!=stop-offset:
                        raise RuntimeError('Browser download chunk length differs')
                    digest.update(chunk)
                    handle.write(chunk)
            if partial.stat().st_size!=size or digest.hexdigest()!=expected_sha256:
                raise RuntimeError('Independent runtime readback SHA256 verification failed')
            partial.rename(destination)
            return {'name':name,'size_bytes':size,'sha256':digest.hexdigest(),
                    'seconds':round(time.perf_counter()-started,3),'independent_readback_verified':True}
        finally:
            partial.unlink(missing_ok=True)
            self.evaluate("(()=>{if(window.__walterXfer?.state!=='working')delete window.__walterXfer;return true})()")
