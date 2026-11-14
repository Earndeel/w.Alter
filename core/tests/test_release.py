import copy,json,os,sys,zipfile,hashlib,base64
from pathlib import Path
import pytest
from walter_platform import release as r

@pytest.fixture
def source(tmp_path):
    root=tmp_path/'source';module=root/'opt/walter-context';module.mkdir(parents=True)
    contract=json.loads(Path('/opt/walter-context/contracts/context.json').read_text())
    contract.update(optional=[],requires=[],anchors=['/opt/walter-context/contracts/context.json','/opt/walter-context/walter_context/core.py'])
    contract['contract']['resources']=[]
    (module/'contracts').mkdir();(module/'contracts/context.json').write_text(json.dumps(contract))
    (module/'walter_context').mkdir();(module/'walter_context/core.py').write_bytes(b'VALUE=42\r\n')
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps({'schema_version':1,'modules':[{'id':'context','manifest':'/opt/walter-context/contracts/context.json'}]}))
    policy=tmp_path/'policy.json';policy.write_text(json.dumps({'version':1,'roots':{'opt/walter-context':['walter_context']},'restored_anchors':[]}))
    return root,module,catalog,policy


def make_bundle(source,tmp_path,**kwargs):
    root,module,catalog,policy=source;dest=tmp_path/'bundle'
    assert r.build(dest,root=root,catalog=catalog,sources=policy,include_dependencies=False,apply=True,**kwargs)['ok']
    return dest


def test_build_preview_has_no_mutation_and_excludes_data_credentials(source,tmp_path):
    root,module,catalog,policy=source
    for rel in ('walter_context/.env','walter_context/gateway.env','walter_context/private.key','walter_context/auth.json','walter_context/archive/private.py','drafts/private.md','sessions/private.json','config/private.json'):
        p=module/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PRIVATE_SENTINEL')
    out=tmp_path/'bundle'
    result=r.build(out,root=root,catalog=catalog,sources=policy,include_dependencies=False)
    assert result['ok'] and not out.exists()
    make_bundle(source,tmp_path)
    assert all(b'PRIVATE_SENTINEL' not in p.read_bytes() for p in out.rglob('*') if p.is_file())
    assert r.inspect(out)['files']==2


def test_complete_preflight_install_bytes_repeat_and_rollback(source,tmp_path):
    bundle=make_bundle(source,tmp_path);root=tmp_path/'target'
    assert r.install(bundle,root)['ok'] and not root.exists()
    result=r.install(bundle,root,apply=True)
    target=root/'opt/walter-context/walter_context/core.py'
    assert target.read_bytes()==b'VALUE=42\r\n'
    assert not r.install(bundle,root,apply=True)['changed']
    assert r.rollback(result['backup'],apply=True)['ok']
    assert not target.exists()


def test_modified_bundle_and_unlisted_wheel_are_refused_before_mutation(source,tmp_path):
    bundle=make_bundle(source,tmp_path);target=tmp_path/'target'
    p=bundle/'payload/opt/walter-context/walter_context/core.py';p.write_text('changed')
    with pytest.raises(ValueError):r.install(bundle,target,apply=True)
    assert not target.exists()


def test_foreign_file_and_source_target_symlink_refused(source,tmp_path):
    bundle=make_bundle(source,tmp_path);root=tmp_path/'target';base=root/'opt/walter-context/walter_context';base.mkdir(parents=True)
    (base/'core.py').write_text('foreign')
    assert not r.install(bundle,root,apply=True)['ok'] and (base/'core.py').read_text()=='foreign'
    other=tmp_path/'outside';other.mkdir();(base/'core.py').unlink();(root/'opt/walter-context/walter_context').rmdir();(root/'opt/walter-context/walter_context').symlink_to(other)
    with pytest.raises(ValueError,match='symlink'):r.install(bundle,root,apply=True)
    assert not list(other.iterdir())


def test_mode_update_rollback_and_human_mode_drift(source,tmp_path):
    bundle=make_bundle(source,tmp_path);root=tmp_path/'target';first=r.install(bundle,root,apply=True)
    target=root/'opt/walter-context/walter_context/core.py';old=target.stat().st_mode&0o777
    manifest=bundle/r.MANIFEST;m=json.loads(manifest.read_text());row=next(x for x in m['files'] if x['path'].endswith('core.py'));row['mode']=0o755;manifest.write_text(json.dumps(m))
    second=r.install(bundle,root,apply=True);assert second['changed'] and target.stat().st_mode&0o777==0o755
    assert r.rollback(second['backup'],apply=True)['ok'] and target.stat().st_mode&0o777==old
    target.chmod(0o400)
    assert not r.rollback(first['backup'],apply=True)['ok']


def test_traversal_duplicate_paths_and_embedded_credentials_refused(source,tmp_path):
    bundle=make_bundle(source,tmp_path);manifest=bundle/r.MANIFEST;m=json.loads(manifest.read_text());original=copy.deepcopy(m)
    for name in ('../escape','/etc/passwd','opt/../escape'):
        m=copy.deepcopy(original);m['files'][0]['path']=name;manifest.write_text(json.dumps(m))
        with pytest.raises(ValueError):r.install(bundle,tmp_path/'target',apply=True)
    m=copy.deepcopy(original);m['files'].append(copy.deepcopy(m['files'][0]));manifest.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='duplicate'):r.inspect(bundle)
    source[1].joinpath('walter_context/core.py').write_text('key="sk-proj-'+('a'*40)+'"')
    with pytest.raises(ValueError,match='credential-like'):r.build(tmp_path/'another',root=source[0],catalog=source[2],sources=source[3],include_dependencies=False)


def test_environment_url_requirement_rejected_before_subprocess(source,tmp_path,monkeypatch):
    bundle=make_bundle(source,tmp_path);p=bundle/r.MANIFEST;m=json.loads(p.read_text())
    m['runtimes']['python']=[{'path':'opt/walter-context/venv','version':[3,12,0],'packages':[['evil @ https://example.invalid/a.whl','1']]}];p.write_text(json.dumps(m))
    monkeypatch.setattr(r,'_command',lambda *a,**k:pytest.fail('subprocess must not run'))
    with pytest.raises(ValueError,match='package identity'):r.environment_plan(bundle,tmp_path/'target')


def wheel(path):
    # Deterministic, pure Python test wheel; no code runs at install.
    name='walter_fixture-1.0-py3-none-any.whl';dist='walter_fixture-1.0.dist-info'
    contents={'walter_fixture/__init__.py':b'VALUE = 42\n',dist+'/METADATA':b'Metadata-Version: 2.1\nName: walter-fixture\nVersion: 1.0\n',
              dist+'/WHEEL':b'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
    rows=[f'{p},sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()+f',{len(data)}' for p,data in contents.items()]
    contents[dist+'/RECORD']=('\n'.join(rows+[dist+'/RECORD,,'])+'\n').encode()
    path.mkdir()
    with zipfile.ZipFile(path/name,'w') as z:
        for p,data in contents.items():z.writestr(p,data)


def test_real_offline_environment_missing_wheel_then_install_and_repeat(source,tmp_path):
    wh=tmp_path/'wheels';wheel(wh);bundle=make_bundle(source,tmp_path,wheelhouse=wh)
    p=bundle/r.MANIFEST;m=json.loads(p.read_text());m['runtimes']['python']=[{'path':'opt/walter-context/venv','version':list(sys.version_info[:3]),'packages':[['walter-fixture','1.0']]}];p.write_text(json.dumps(m))
    root=tmp_path/'target';assert r.environment_plan(bundle,root)['ok'] and not root.exists()
    result=r.install_environments(bundle,root,apply=True);assert result['ok'] and result['applied']
    env=root/'opt/walter-context/venv';assert json.loads(r._command([str(env/'bin/python'),'-I','-c','import walter_fixture,json; print(json.dumps({"value":walter_fixture.VALUE,"file":walter_fixture.__file__}))']))['file'].startswith(str(root))
    assert not r.install_environments(bundle,root,apply=True)['applied']
    metadata=next(env.glob('lib/python*/site-packages/walter_fixture-1.0.dist-info/METADATA'))
    metadata.write_text(metadata.read_text().replace('Version: 1.0','Version: 9.0'))
    assert not r.environment_plan(bundle,root)['ok']
    # Extra untracked artifacts cannot be offered to pip.
    (bundle/'wheelhouse/extra.whl').write_bytes(b'x')
    with pytest.raises(ValueError,match='undeclared'):r.environment_plan(bundle,root)
    (bundle/'wheelhouse/extra.whl').unlink()
    p.write_text(json.dumps({**m,'wheels':[]}))
    (bundle/'wheelhouse'/next(iter(wh.iterdir())).name).unlink()
    assert not r.environment_plan(bundle,tmp_path/'new-target')['ok']


def test_source_allowlist_symlink_cannot_read_outside(source,tmp_path):
    source[1].joinpath('walter_context/core.py').unlink();secret=tmp_path/'outside';secret.write_text('PRIVATE_SENTINEL')
    source[1].joinpath('walter_context/core.py').symlink_to(secret)
    with pytest.raises(ValueError,match='anchor excluded'):make_bundle(source,tmp_path)


def test_bundle_changed_after_inspection_never_installs(source,tmp_path,monkeypatch):
    bundle=make_bundle(source,tmp_path);old=r._inspect
    def changed(p):
        result=old(p)
        (bundle/'payload/opt/walter-context/walter_context/core.py').write_text('NEW_UNVERIFIED_CONTENT')
        return result
    monkeypatch.setattr(r,'_inspect',changed)
    root=tmp_path/'target'
    with pytest.raises(ValueError,match='changed during'):r.install(bundle,root,apply=True)
    assert not root.exists()


def test_service_units_are_packaged_but_never_started(source,tmp_path):
    root,module,catalog,policy=source
    unit=module/'worker.service';unit.write_text('[Service]\nExecStart=/opt/walter-context/bin/worker\n')
    p=json.loads(policy.read_text());p['roots']['opt/walter-context'].append('worker.service');policy.write_text(json.dumps(p))
    bundle=make_bundle(source,tmp_path);target=tmp_path/'target';r.install(bundle,target,apply=True)
    assert (target/'opt/walter-context/worker.service').read_text()==unit.read_text()


def test_missing_anchor_or_owner_contract_mismatch_refused(source,tmp_path):
    bundle=make_bundle(source,tmp_path);p=bundle/r.MANIFEST;m=json.loads(p.read_text())
    original=copy.deepcopy(m);m['files']=[row for row in m['files'] if not row['path'].endswith('core.py')];p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='anchors'):r.inspect(bundle)
    m=original;m['modules']['modules'][0]['limitations'].append('manifest drift');p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='owner contract'):r.inspect(bundle)


def test_incompatible_wheel_never_declared_ready(source,tmp_path):
    wh=tmp_path/'wheels';wheel(wh);old=next(wh.iterdir());old.rename(wh/'walter_fixture-1.0-cp999-none-any.whl')
    bundle=make_bundle(source,tmp_path,wheelhouse=wh);p=bundle/r.MANIFEST;m=json.loads(p.read_text())
    m['runtimes']['python']=[{'path':'opt/walter-context/venv','version':list(sys.version_info[:3]),'packages':[['walter-fixture','1.0']]}];p.write_text(json.dumps(m))
    result=r.environment_plan(bundle,tmp_path/'target')
    assert not result['ok'] and result['environments'][0]['missing_wheels']==['walter-fixture==1.0']


def test_module_policy_follows_declared_walter_root_after_layout_migration(source,tmp_path):
    root,module,catalog,policy=source
    destination=root/'walter/context';destination.parent.mkdir();module.rename(destination)
    p=destination/'contracts/context.json';p.write_text(p.read_text().replace('/opt/walter-context','/walter/context'))
    catalog.write_text(catalog.read_text().replace('/opt/walter-context','/walter/context'))
    policy.write_text(json.dumps({'version':1,'modules':{'context':['walter_context']},'restored_module_anchors':{}}))
    bundle=tmp_path/'bundle'
    assert r.build(bundle,root=root,catalog=catalog,sources=policy,include_dependencies=False,apply=True)['ok']
    assert r.inspect(bundle)['ok']
    target=tmp_path/'target';assert r.install(bundle,target,apply=True)['ok']
    assert (target/'walter/context/walter_context/core.py').read_bytes()==b'VALUE=42\r\n'


def test_mixed_python_versions_can_be_prepared_as_explicit_selections(source,tmp_path):
    bundle=make_bundle(source,tmp_path);p=bundle/r.MANIFEST;m=json.loads(p.read_text())
    m['runtimes']['python']=[{'path':'opt/walter-context/venv','version':list(sys.version_info[:3]),'packages':[]},
                            {'path':'opt/walter-context/alternate/.venv','version':[3,99,0],'packages':[]}]
    p.write_text(json.dumps(m));target=tmp_path/'target'
    assert not r.environment_plan(bundle,target)['ok']
    result=r.environment_plan(bundle,target,environments=['opt/walter-context/venv'])
    assert result['ok'] and not result['all_environments_selected']
    assert result['not_selected']==['opt/walter-context/alternate/.venv']
    with pytest.raises(ValueError,match='selection'):r.environment_plan(bundle,target,environments=['unknown'])
