import importlib.util,io,json,pathlib,sqlite3,sys,tarfile
import pytest
from walter_memory import backup_bundle as B

def tree(tmp):
    root=tmp/'root';mod=root/'opt/walter-memory';mod.mkdir(parents=True)
    (mod/'code.py').write_text('source preserved')
    (mod/'models').mkdir();(mod/'models'/'schema.py').write_text('code directory named models must survive')
    (mod/'venv').mkdir();(mod/'venv'/'binary').write_text('rebuild')
    link=root/'user/instance/plugins/memory';link.parent.mkdir(parents=True);link.symlink_to('/opt/walter-memory')
    (root/'user/instance').chmod(0o700)
    return root

def test_bundle_preserves_modules_links_and_private_modes(tmp_path):
    root=tree(tmp_path);out=tmp_path/'bundle.tar'
    result=B.create(out,root,['opt/walter-memory','user/instance/plugins'],['opt/walter-memory/code.py','user/instance/plugins/memory'],False)
    assert result['ok'] and result['sqlite_snapshots']==0
    assert out.stat().st_mode & 0o777==0o600
    with tarfile.open(out) as t:
        assert 'opt/walter-memory/venv/binary' not in t.getnames()
        assert t.extractfile('opt/walter-memory/models/schema.py').read().startswith(b'code directory')
        assert t.getmember('user/instance/plugins/memory').issym()
        assert t.getmember('user/instance').mode==0o700

def test_missing_required_integration_fails_before_archive(tmp_path):
    root=tree(tmp_path);out=tmp_path/'bundle.tar'
    with pytest.raises(RuntimeError,match='missing'):B.create(out,root,['opt/walter-memory'],['missing.env'],False)
    assert not out.exists()

def test_inventory_discovers_new_modules_and_external_service_credentials(tmp_path):
    root=tmp_path/'root'
    for m in B.CORE_MODULES:(root/f'opt/walter-{m}').mkdir(parents=True)
    for m,entry in B.MODULE_ANCHORS.items():
        p=root/f'opt/walter-{m}'/entry;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('example')
    (root/'opt/walter-new-module').mkdir()
    for name in ['root/.hermes/config.yaml','root/.hermes/.env','root/.pgpass',
                 'root/.hermes/walter-llm/module.env','root/.config/rclone/rclone.conf',
                 'root/.config/systemd/user/hermes-gateway.service','opt/openclaw/hermes_voice_bridge.py',
                 'etc/walter-auth/gateway.env']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('example')
    unit=root/'etc/systemd/system/walter-example.service';unit.parent.mkdir(parents=True)
    unit.write_text('[Service]\nEnvironmentFile=/etc/walter-auth/gateway.env\n')
    sources,required,absent=B.inventory(root)
    assert 'opt/walter-new-module' in sources
    assert not any(r.startswith('root/.hermes') for r in required)   # Walter needs no Hermes file (2026-11-11)
    assert 'etc/walter-auth/gateway.env' in sources and 'etc/walter-auth/gateway.env' in required
    (root/'etc/walter-auth/gateway.env').unlink()
    with pytest.raises(RuntimeError,match='EnvironmentFile missing'):B.inventory(root)

def test_verification_rejects_missing_member_and_content_corruption(tmp_path):
    root=tree(tmp_path);out=tmp_path/'bundle.tar';B.create(out,root,['opt/walter-memory'],['opt/walter-memory/code.py'],False)
    for change in ['drop','corrupt','permissions']:
        altered=tmp_path/(change+'.tar')
        with tarfile.open(out) as src,tarfile.open(altered,'w') as dst:
            for item in src:
                data=src.extractfile(item).read() if item.isfile() else None
                if item.name=='opt/walter-memory/code.py':
                    if change=='drop':continue
                    if change=='corrupt':data=b'X'*item.size
                    if change=='permissions':item.mode=0o777
                dst.addfile(item,io.BytesIO(data) if data is not None else None)
        with pytest.raises(ValueError):B.verify(altered)
    with pytest.raises(ValueError,match='required paths missing'):B.verify(out,['opt/walter-missing'])
