"""Private immutable Drive cache store; auth stays on the agent VM."""
from pathlib import Path
import hashlib
import re
import tempfile
from transfer import CHUNK, MAX_BYTES, iter_chunks, safe_filename, sha256_file

class _BoundedWriter:
    """Reject a metadata-size overrun before writing or requesting another chunk."""
    def __init__(self, handle, limit):
        self.handle,self.limit=handle,limit

    def write(self, data):
        if self.handle.tell()+len(data)>self.limit:
            raise RuntimeError('Drive stream exceeds pinned byte size')
        return self.handle.write(data)

class DriveStore:
    def __init__(self, folder):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        if not re.fullmatch(r'[A-Za-z0-9_-]+', folder):
            raise ValueError('Invalid Drive folder identifier')
        self.folder=folder
        credentials=Credentials.from_authorized_user_file(str(Path.home()/'.hermes/google_token.json'))
        self.service=build('drive','v3',credentials=credentials,cache_discovery=False)
        meta=self.service.files().get(fileId=folder,fields='id,mimeType,trashed,permissions(type,role)').execute()
        self.require_private(meta)
        if meta.get('mimeType')!='application/vnd.google-apps.folder':
            raise ValueError('Cache target is not a Drive folder')

    @staticmethod
    def require_private(meta):
        permissions=meta.get('permissions',[])
        if meta.get('trashed') or not permissions or any(p['type']!='user' for p in permissions):
            raise ValueError('Refusing trashed, public or group-shared cache storage')

    def find(self, name):
        name=safe_filename(name)
        items=[]
        token=None
        while True:
            response=self.service.files().list(q=f"'{self.folder}' in parents and name='{name}' and trashed=false",
                fields='nextPageToken,files(id,name,size,appProperties)',pageSize=100,pageToken=token).execute()
            items.extend(response.get('files',[]))
            token=response.get('nextPageToken')
            if not token:break
        if len(items)>1:
            raise ValueError('Ambiguous duplicate cache file names; refusing automatic selection')
        return items[0] if items else None

    def fetch(self, name, destination):
        from googleapiclient.http import MediaIoBaseDownload
        record=self.find(name)
        if record is None:
            raise FileNotFoundError('Private cache object absent')
        meta=self.service.files().get(fileId=record['id'],fields='id,name,size,md5Checksum,appProperties,trashed,permissions(type,role)').execute()
        self.require_private(meta)
        size=int(meta.get('size',-1))
        expected=meta.get('appProperties',{}).get('walterSha256','')
        if not 0<=size<=MAX_BYTES or not re.fullmatch(r'[0-9a-f]{64}',expected):
            raise ValueError('Cache object missing pinned checksum or outside transfer limit')
        destination=Path(destination)
        partial=destination.with_name(destination.name+'.part')
        if destination.exists() or destination.is_symlink() or partial.exists() or partial.is_symlink():
            raise ValueError('Refusing overwrite of a local cache download')
        destination.parent.mkdir(parents=True,exist_ok=True)
        try:
            with partial.open('xb') as handle:
                download=MediaIoBaseDownload(_BoundedWriter(handle,size),self.service.files().get_media(fileId=record['id']),chunksize=4*CHUNK)
                done=False
                while not done:_,done=download.next_chunk(num_retries=2)
            checksum=sha256_file(partial)
            md5=hashlib.md5(usedforsecurity=False)
            for chunk in iter_chunks(partial):md5.update(chunk)
            if (checksum!=expected or partial.stat().st_size!=size
                    or md5.hexdigest()!=meta.get('md5Checksum')):
                raise RuntimeError('Drive independent checksum readback failed')
            partial.rename(destination)
            return {'id':meta['id'],'name':meta['name'],'size_bytes':size,'sha256':checksum,
                    'private':True,'independent_drive_readback_verified':True}
        finally:
            partial.unlink(missing_ok=True)

    def save(self, source):
        from googleapiclient.http import MediaFileUpload
        source=Path(source)
        name=safe_filename(source.name)
        if source.is_symlink() or not source.is_file() or not 1<=source.stat().st_size<=MAX_BYTES:
            raise ValueError('Cache save requires a nonempty regular file within transfer limit')
        checksum=sha256_file(source)
        existing=self.find(name)
        if existing:
            if existing.get('appProperties',{}).get('walterSha256')!=checksum:
                raise ValueError('Immutable cache name collision; choose an explicit new version')
        else:
            existing=self.service.files().create(body={'name':name,'parents':[self.folder],
                'mimeType':'application/octet-stream','appProperties':{'walterPurpose':'colab-cache-no-mount','walterSha256':checksum}},
                media_body=MediaFileUpload(str(source),mimetype='application/octet-stream',chunksize=4*CHUNK,resumable=True),
                fields='id,name,size,appProperties').execute()
        scratch=Path.home()/'.hermes/cache/scratch/colab-no-mount'
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='drive-readback-',dir=scratch) as root:
            verified=self.fetch(name,Path(root)/name)
        if verified['id']!=existing['id'] or verified['sha256']!=checksum:
            raise RuntimeError('Readback differs from the exact saved Drive object')
        return verified
