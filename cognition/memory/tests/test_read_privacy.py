"""Cloud facade privacy: canonical events and raw vault metadata/bytes."""
import ast
import hashlib
from contextlib import contextmanager
from pathlib import Path

import pytest
from walter_memory import cli, events, objects


def test_events_cli_cloud_scope(monkeypatch, capsys):
    received=[]
    monkeypatch.setattr(events,'get_events',lambda **kw: received.append(kw) or [])
    cli.main(['events','--cloud-safe','--limit','2'])
    assert received[-1]['max_privacy']=='cloud_allowed'
    cli.main(['events','--limit','2'])
    assert received[-1]['max_privacy']=='local_only'


@pytest.mark.parametrize('scope',['local_only','redacted_cloud',None])
def test_vault_denies_restricted_or_unclassified_bytes_before_mkdir_or_s3(monkeypatch,tmp_path,scope):
    monkeypatch.setattr(objects,'find',lambda _: {'privacy_class':scope,'original_name':'private.txt'})
    monkeypatch.setattr(objects,'s3',lambda: pytest.fail('S3 must not be reached'))
    dest=tmp_path/'must-not-exist'
    with pytest.raises(PermissionError):
        objects.get_object('fixture',dest_dir=dest,max_privacy='cloud_allowed')
    assert not dest.exists()


def test_cloud_allowed_vault_download_preserves_integrity(monkeypatch,tmp_path):
    payload=b'public fixture'
    digest=hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(objects,'find',lambda _: {'privacy_class':'cloud_allowed','original_name':'public.txt',
        'sha256':digest,'storage_zone':'clear','storage_key':'fixture'})
    class S3:
        def download_file(self,bucket,key,path): Path(path).write_bytes(payload)
    monkeypatch.setattr(objects,'s3',lambda: S3())
    path=objects.get_object('fixture',dest_dir=tmp_path/'out',max_privacy='cloud_allowed')
    assert path.read_bytes()==payload


def test_metadata_search_filters_in_database_before_snippets(monkeypatch):
    seen=[]
    class Conn:
        def execute(self,sql,args):
            seen.append((sql,args)); return self
        def fetchall(self): return []
    @contextmanager
    def connection(): yield Conn()
    monkeypatch.setattr(objects,'connection',connection)
    objects.search('needle',max_privacy='cloud_allowed')
    sql,args=seen[-1]
    assert 'privacy_class = any(%s)' in sql
    assert args[0]==['cloud_allowed']


def test_vault_cli_passes_scope_to_search_and_bytes(monkeypatch,capsys):
    received=[]
    monkeypatch.setattr(objects,'search',lambda *a,**kw:received.append(kw) or [])
    monkeypatch.setattr(objects,'get_object',lambda *a,**kw:received.append(kw) or '/fixture')
    cli.main(['objects','search','--cloud-safe'])
    assert received[-1]['max_privacy']=='cloud_allowed'
    cli.main(['objects','get','fixture','--cloud-safe','--dest-dir','/fixture-directory'])
    assert received[-1]['max_privacy']=='cloud_allowed'
    assert received[-1]['dest_dir']=='/fixture-directory'


def test_mcp_cloud_facades_enforce_flags_without_materializing_vault_directory(monkeypatch,tmp_path):
    # Load just public functions to avoid starting an MCP host or auth clients.
    source=Path('/opt/walter-core/server.py').read_text()
    tree=ast.parse(source)
    selected=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in {'memory_events','vault_search','vault_get'}:
            node.decorator_list=[]; selected.append(node)
    calls=[]
    namespace={'_walter_memory':lambda *a,**kw:calls.append(a) or '[]','Path':Path}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<MCP privacy facades>','exec'),namespace)
    namespace['memory_events'](text='fixture')
    namespace['vault_search'](text='fixture')
    dest=tmp_path/'must-not-exist'
    namespace['vault_get']('fixture',str(dest))
    assert len(calls)==3 and all('--cloud-safe' in args for args in calls)
    assert '--dest-dir' in calls[-1]
    assert not dest.exists()
