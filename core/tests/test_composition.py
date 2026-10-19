import copy,json,os,sys
from pathlib import Path
import pytest
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from walter_platform import composition as c
from walter_platform import harness_transaction as tx

@pytest.fixture
def home(tmp_path,monkeypatch):
    identity=tmp_path/'identity.md';identity.write_text('Synthetic Walter identity\n')
    skill=tmp_path/'SKILL.md';skill.write_text('Synthetic skill\n')
    credentials=tmp_path/'credentials.yaml';credentials.write_text('test-only: true\n')
    get=c.definition
    def definition(host):
        d=copy.deepcopy(get(host));d.update(identity_source=str(identity),skill_source=str(skill),credential_source=str(credentials));return d
    monkeypatch.setattr(c,'definition',definition)
    target=tmp_path/'home';target.mkdir();return target

@pytest.mark.parametrize('host',['codex','claude-code','dsh','hermes'])
def test_preview_idempotent_install_and_full_rollback(home,host):
    if host=='hermes':(home/'config.yaml').write_text('memory:\n  provider: hindsight\n')
    original={str(p):p.read_bytes() for p in home.rglob('*') if p.is_file()}
    before=list(home.rglob('*'))
    preview=c.install(host,home)
    assert preview['ok'] and preview['changed'] and not preview['applied']
    assert list(home.rglob('*'))==before
    result=c.install(host,home,apply=True,backup_root=home.parent/'backups')
    assert result['applied']
    assert not c.install(host,home)['changed']
    rollback=c.rollback(result['backup'])
    assert rollback['ok'] and not rollback['applied']
    assert c.rollback(result['backup'],apply=True)['applied']
    assert {str(p):p.read_bytes() for p in home.rglob('*') if p.is_file()}==original
    assert not any(p.is_symlink() for p in home.rglob('*'))

def test_fresh_hermes_requires_explicit_memory_provider_without_silently_selecting_legacy(home):
    result=c.install('hermes',home,apply=True)
    assert not result['ok'] and not result['applied']
    assert not (home/'config.yaml').exists()

def test_selected_hermes_provider_does_not_require_general_plugin_enable(home):
    (home/'config.yaml').write_text('memory:\n  provider: walter-memory\n')
    result=c.install('hermes',home,apply=True,backup_root=home.parent/'b')
    assert result['ok']
    data=yaml.safe_load((home/'config.yaml').read_text())
    assert data['memory']['provider']=='walter-memory' and 'walter-memory' not in data['plugins']['enabled']
    assert (home/'plugins/walter-memory/__init__.py').is_file()
    assert not c.install('hermes',home)['changed']

def test_codex_does_not_replace_native_model_or_global_identity(home):
    p=home/'config.toml';p.write_text('model="native-model"\napproval_policy="on-request"\n[mcp_servers.other]\ncommand="other"\n')
    global_identity=home/'AGENTS.md';global_identity.write_text('Operator instructions')
    c.install('codex',home,apply=True,backup_root=home.parent/'b')
    import tomllib
    d=tomllib.loads(p.read_text());assert d['model']=='native-model' and d['approval_policy']=='on-request'
    assert d['mcp_servers']['other']['command']=='other'
    assert global_identity.read_text()=='Operator instructions'
    assert (home/'walter-profile/AGENTS.md').exists()

def test_codex_custom_notify_is_explicit_conflict(home):
    p=home/'config.toml';p.write_text('notify=["foreign"]\n')
    with pytest.raises(ValueError,match='notify hook conflicts'):c.install('codex',home,apply=True)
    assert p.read_text()=='notify=["foreign"]\n'
    assert not (home/'walter-profile').exists()

def test_claude_preserves_unrelated_hooks_and_permissions(home):
    p=home/'settings.json';p.write_text(json.dumps({'hooks':{'Stop':[{'hooks':[{'type':'command','command':'other'}]}]},'permissions':{'deny':['Bash(rm:*)']}}))
    c.install('claude-code',home,apply=True,backup_root=home.parent/'b')
    d=json.loads(p.read_text());assert d['permissions']=={'deny':['Bash(rm:*)']}
    assert d['hooks']['Stop'][0]['hooks'][0]['command']=='other'

def test_dsh_merges_other_provider_and_skill_dir(home):
    p=home/'cordis.patch.yml';p.write_text(yaml.safe_dump([{'id':'llm-pi-ai','config':{'providers':{'other':{'custom':'keep'}}}},{'id':'skill-filesystem','config':{'customSkillDirs':['/other/skills']}}]))
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    d=yaml.safe_load(p.read_text());provider=next(x for x in d if x.get('id')=='llm-pi-ai')['config']['providers']
    assert provider['other']=={'custom':'keep'} and 'walter' in provider
    assert next(x for x in d if x.get('id')=='skill-filesystem')['config']['customSkillDirs']==['/other/skills',c.SKILL_DIR]
    assert not c.install('dsh',home)['changed']

def test_hermes_unqualified_context_never_activated(home):
    p=home/'config.yaml';p.write_text('context:\n  engine: custom-engine\n')
    with pytest.raises(ValueError,match='no unqualified'):c.install('hermes',home,apply=True)
    assert p.read_text()=='context:\n  engine: custom-engine\n'

def test_changed_file_blocks_entire_rollback(home):
    result=c.install('codex',home,apply=True,backup_root=home.parent/'b')
    p=home/'config.toml';p.write_text(p.read_text()+'\n# human change\n')
    result2=c.rollback(result['backup'],apply=True)
    assert not result2['ok'] and not result2['applied']
    assert (home/'walter-profile/AGENTS.md').exists() and '# human change' in p.read_text()

def test_existing_symlink_mode_and_original_content_restored(home):
    real=home.parent/'actual.toml';real.write_text('model="native"\n');real.chmod(0o640)
    p=home/'config.toml';p.symlink_to(real)
    result=c.install('codex',home,apply=True,backup_root=home.parent/'b')
    assert p.is_symlink() and real.stat().st_mode&0o777==0o640
    assert c.rollback(result['backup'],apply=True)['ok']
    assert p.is_symlink() and real.read_text()=='model="native"\n' and real.stat().st_mode&0o777==0o640

def test_partial_write_failure_rolls_back_completed_files(home,monkeypatch):
    original=tx.atomic
    def fail(path,*args,**kwargs):
        if Path(path).name=='config.toml':raise OSError('synthetic failure')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(tx,'atomic',fail)
    with pytest.raises(RuntimeError,match='composition write failed'):c.install('codex',home,apply=True,backup_root=home.parent/'b')
    assert not (home/'walter-profile/AGENTS.md').exists()
    assert not (home/'skills/walter-skills/SKILL.md').exists()

def test_previews_and_manifests_never_serialize_config_values(home):
    p=home/'config.toml';p.write_text('private_fixture="DO_NOT_PRINT_THIS"\n')
    result=c.install('codex',home,apply=True,backup_root=home.parent/'b')
    assert 'DO_NOT_PRINT_THIS' not in json.dumps(result)
    manifest=Path(result['backup'])/'manifest.json'
    assert 'DO_NOT_PRINT_THIS' not in manifest.read_text()
    assert all(x.stat().st_mode&0o077==0 for x in manifest.parent.iterdir())

def test_managed_identity_drift_is_not_overwritten(home):
    c.install('codex',home,apply=True,backup_root=home.parent/'b')
    p=home/'walter-profile/AGENTS.md';p.write_text(p.read_text().replace('Synthetic Walter','Locally edited'))
    with pytest.raises(ValueError,match='edited'):c.install('codex',home,apply=True)

def test_configuration_changed_after_preview_cannot_commit(home):
    _,changes,_,_=c._plan('codex',home)
    p=home/'config.toml';p.write_text('model="foreign-change"\n')
    with pytest.raises(RuntimeError,match='changed during preparation'):tx.commit(changes,backup_root=home.parent/'b',host='codex')
    assert p.read_text()=='model="foreign-change"\n'

def test_recovery_of_interrupted_intent_before_write(home):
    p=home/'config.toml';p.write_text('model="original"\n')
    result=c.install('codex',home,apply=True,backup_root=home.parent/'b')
    root=Path(result['backup']);mp=root/'manifest.json';manifest=json.loads(mp.read_text())
    # Simulate a crash after intent was journaled, before this write happened.
    row=next(r for r in manifest['files'] if r['path']==str(p))
    p.write_bytes((root/row['before_file']).read_bytes());manifest['state']='applying'
    mp.write_text(json.dumps(manifest))
    assert c.rollback(root,apply=True)['ok']
    assert p.read_text()=='model="original"\n'

def test_disabled_dsh_plugin_overlay_is_not_bypassed(home):
    p=home/'cordis.patch.yml';p.write_text('- id: hooks-walter\n  disabled: true\n')
    with pytest.raises(ValueError,match='separate override'):c.install('dsh',home,apply=True)

def test_matrix_does_not_infer_usage_or_qualification_from_configs(home,monkeypatch):
    from walter_platform import harness_matrix as m
    monkeypatch.setattr(m,'COMPOSITIONS',home)
    matrix=m.matrix()
    assert len(matrix['bindings'])==36
    assert all(r['in_use'] is None and r['qualified'] is None for r in matrix['bindings'])
