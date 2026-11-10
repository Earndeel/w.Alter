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
    neutral=c.engine_values(instance=False)   # never the live instance's values in tests
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(neutral))
    target=tmp_path/'home';target.mkdir();return target

@pytest.mark.parametrize('host',['codex','claude-code','dsh','hermes'])
def test_preview_idempotent_install_and_full_rollback(home,host):
    if host=='hermes':(home/'config.yaml').write_text('memory:\n  provider: walter-memory\n')
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

def test_dsh_merges_other_provider_and_turns_off_dsh_skills(home):
    p=home/'cordis.patch.yml';p.write_text(yaml.safe_dump([{'id':'llm-pi-ai','config':{'providers':{'other':{'custom':'keep'}}}},{'id':'skill-filesystem','config':{'customSkillDirs':['/other/skills']}}]))
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    d=yaml.safe_load(p.read_text());provider=next(x for x in d if x.get('id')=='llm-pi-ai')['config']['providers']
    assert provider['other']=={'custom':'keep'} and 'walter' in provider
    assert {m['id'] for m in provider['walter']['models']}>=set(c.DSH_TASKS)
    skill=next(x for x in d if x.get('id')=='skill-filesystem')   # skills = walter-skills; local config kept, row off
    assert skill['disabled'] is True and skill['config']['customSkillDirs']==['/other/skills']
    assert not c.install('dsh',home)['changed']

def test_dsh_is_runtime_only(home):
    """Lot 1 (2026-11-07): no DSH identity, skills, web, compaction, title model or DeepSeek service stays on."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    d=yaml.safe_load((home/'cordis.patch.yml').read_text());rows={x['id']:x for x in d if 'id' in x}
    assert all(rows[ident]['disabled'] is True for ident in c.DSH_OFF)
    assert rows['system-prompt']['config']=={'includeHarnessIdentity':False,'personaPrefix':'','personaSuffix':''}
    assert rows['session-title-llm']['config']['provider']=='walter' and rows['session-title-llm']['config']['model'] in c.DSH_TASKS
    assert not any(e.get('id')=='walter-context' for r in d for e in r.get('insert',[]))   # mounted per profile
    web=c._dsh_yaml((home/'profiles'/'web'/'cordis.patch.yml').read_text())
    preset=next(x for x in web if x.get('id')=='preset-standard')['config'];flat=json.dumps(preset)
    assert preset['id']=='standard' and c._context_port() in flat and '__js__' not in flat
    for owned in ('dsh-persona"','dsh-skill-filesystem"','dsh-tool-skill"','dsh-tool-web"','dsh-compaction-basic"'):assert owned not in flat
    assert next(x for x in web if x.get('id')=='web-runtime')['config']['surfaceContext'] is False
    assert all(next(x for x in web if x.get('id')==ident)['disabled'] is True for ident in c.DSH_WEB_OFF)
    assert c._context_port() in (home/'profiles'/'headless'/'cordis.patch.yml').read_text()
    assert not c.install('dsh',home)['changed']

def test_dsh_removes_pre_lot1_global_context_row(home):
    p=home/'cordis.patch.yml';p.write_text(yaml.safe_dump([{'insert':[{'id':'walter-context','name':c._context_port()}]}]))
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    assert not any(e.get('id')=='walter-context' for r in yaml.safe_load(p.read_text()) for e in r.get('insert',[]))

def test_dsh_profile_section_edited_by_hand_is_not_overwritten(home):
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    wp=home/'profiles'/'web'/'cordis.patch.yml';wp.write_text(wp.read_text().replace('surfaceContext: false','surfaceContext: true'))
    with pytest.raises(ValueError,match='edited'):c.install('dsh',home)

def _dsh_rewrite(text,append=True):
    """What DSH web does when it saves a UI setting: re-serialises the file (other indentation, comments inside
    the rows dropped) and appends its row at the end of the document, i.e. before the trailing fence."""
    start=text.index('# walter:dsh-web');end=text.index('# /walter:dsh-web')
    header,_,body=text[start:end].partition('\n')
    class Dumper(yaml.SafeDumper):
        def increase_indent(self,flow=False,indentless=False):return super().increase_indent(flow,False)
    Dumper.add_representer(dict,lambda d,v:d.represent_scalar('tag:yaml.org,2002:js',v['__js__']) if set(v)=={'__js__'} else d.represent_dict(v))
    rows=c._dsh_yaml(body)+([{'id':'ui-settings-general','name':'@deepseek-ai/dsh-client-ui-settings-general','config':{'welcomeNoticeVersion':'2026-09-28.1'}}] if append else [])
    return text[:start]+header+'\n'+yaml.dump(rows,Dumper=Dumper,sort_keys=False,allow_unicode=True,width=120)+'\n'+text[end:]

def test_dsh_profile_rewritten_by_dsh_keeps_its_row_and_stays_managed(home):
    """2026-11-07: DSH re-serialised the web profile and appended ui-settings-general inside the Walter fence;
    the installer refused every later install. Format and foreign rows are not hand edits of Walter rows."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    wp=home/'profiles'/'web'/'cordis.patch.yml';walter=c._dsh_yaml(wp.read_text())
    wp.write_text(_dsh_rewrite(wp.read_text()))
    assert c._dsh_yaml(wp.read_text())[:len(walter)]==walter
    c.install('dsh',home,apply=True,backup_root=home.parent/'b2')
    rows=c._dsh_yaml(wp.read_text())
    assert next(x for x in rows if x.get('id')=='ui-settings-general')['config']['welcomeNoticeVersion']
    head,_,tail=wp.read_text().partition('# /walter:dsh-web')
    assert 'ui-settings-general' in tail and 'ui-settings-general' not in head   # moved out of the block
    assert not c.install('dsh',home)['changed']
    wp.write_text(_dsh_rewrite(wp.read_text(),append=False))                      # again, with the new header
    assert c.install('dsh',home,apply=True,backup_root=home.parent/'b3')['ok']
    assert sum(x.get('id')=='ui-settings-general' for x in c._dsh_yaml(wp.read_text()))==1

def test_dsh_profile_rewritten_then_edited_by_hand_is_refused(home):
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    wp=home/'profiles'/'web'/'cordis.patch.yml'
    c.install('dsh',home,apply=True,backup_root=home.parent/'b1')
    wp.write_text(_dsh_rewrite(wp.read_text()).replace('surfaceContext: false','surfaceContext: true'))
    with pytest.raises(ValueError,match='edited'):c.install('dsh',home)

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


def _web(home):
    return (home/'profiles'/'web'/'cordis.patch.yml').read_text()


def test_dsh_face_is_rendered_from_engine_values_before_the_web_block(home,monkeypatch):
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    text=_web(home)
    assert 0<=text.index('# walter:dsh-face ')<text.index('# walter:dsh-web ')
    rows=c._dsh_yaml(text)
    assert rows[0]['config']['cookieMaxAgeDays']==30 and rows[0]['config']['trustedHosts']=={'__js__':'ctx.webRuntime.trustedHosts'}
    assert rows[1]['insert'][0]['id']=='walter-ui' and rows[1]['insert'][0]['config']['name']=='Walter'
    values=c.engine_values()
    values['dsh']['web'].update(name='Instance « X »',tagline="L'accueil",cookie_max_age_days=365)
    values['dsh']['model_names']={'coding':'Code · agent'}
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(values))
    assert c.install('dsh',home)['changed']
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    rows=c._dsh_yaml(_web(home))
    assert rows[0]['config']['cookieMaxAgeDays']==365
    assert rows[1]['insert'][0]['config']=={'name':'Instance « X »','tagline':"L'accueil"}
    models=[r for r in c._dsh_yaml((home/'cordis.patch.yml').read_text()) if r.get('id')=='llm-pi-ai'][0]['config']['providers']['walter']['models']
    assert {m['id']:m['name'] for m in models}['coding']=='Code · agent'
    provider=[r for r in c._dsh_yaml((home/'cordis.patch.yml').read_text()) if r.get('id')=='llm-pi-ai'][0]['config']['providers']['walter']
    assert provider['cacheRetention']=='long' and provider['compat']=={'supportsLongCacheRetention':True}
    assert _web(home).count('# walter:dsh-face ')==1 and not c.install('dsh',home)['changed']


def test_hand_written_face_rows_are_a_conflict_not_a_second_copy(home):
    web=home/'profiles'/'web';web.mkdir(parents=True)
    (web/'cordis.patch.yml').write_text('- id: connection\n  config:\n    cookieMaxAgeDays: 365\n')
    with pytest.raises(ValueError,match='hand-written'):c.install('dsh',home)
    (web/'cordis.patch.yml').write_text('- insert:\n  - id: walter-ui\n    name: /x/index.js\n')
    with pytest.raises(ValueError,match='hand-written'):c.install('dsh',home)


def test_dsh_face_edited_by_hand_is_refused_and_bad_values_fail(home,monkeypatch):
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    p=home/'profiles'/'web'/'cordis.patch.yml'
    p.write_text(p.read_text().replace('cookieMaxAgeDays: 30','cookieMaxAgeDays: 9999'))
    with pytest.raises(ValueError,match='edited'):c.install('dsh',home)
    values=c.engine_values();values['dsh']['web']['cookie_max_age_days']='365'
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(values))
    with pytest.raises(ValueError,match='positive integer'):c._dsh_face(values)


def _engine(home):
    d=c._dsh_yaml((home/'cordis.patch.yml').read_text())
    rows={e['id']:e for r in d for e in r.get('insert',[])}
    hooks=json.loads((home/'walter-hooks.json').read_text())['hooks']
    return rows,hooks

def test_engine_intake_switch_hook_shadow_native_and_back(home,monkeypatch):
    """Lot E2 (2026-11-10): `hook` = the E1 composition untouched; `shadow` adds the observing plugins beside the hook;
    `native` gives UserPromptSubmit/Stop to the plugins and drops the owner-turn adapter; back to `hook` restores it."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    e1=(home/'cordis.patch.yml').read_bytes(),(home/'walter-hooks.json').read_bytes()
    values=c.engine_values()
    def mode(m):
        v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']={'intake':m}
        monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
        c.install('dsh',home,apply=True,backup_root=home.parent/'b')
        assert not c.install('dsh',home)['changed']           # idempotent in every mode
        return _engine(home)
    rows,hooks=mode('shadow')
    assert rows['walter-intake']['config']['mode']=='shadow' and rows['walter-events']['config']['mode']=='shadow'
    assert rows['walter-intake']['name'].endswith('engine/plugins/intake/index.mjs') and 'walter-owner-turn' in rows
    assert {'UserPromptSubmit','Stop','SessionStart','PostToolUse'}<=set(hooks)
    assert rows['walter-intake']['config']['tokenFile'].endswith('.env') and 'state/runs/current' in rows['walter-intake']['config']['runsDir']
    rows,hooks=mode('native')
    assert rows['walter-intake']['config']['mode']=='native' and 'walter-owner-turn' not in rows
    assert 'UserPromptSubmit' not in hooks and 'Stop' not in hooks and {'SessionStart','PostToolUse'}<=set(hooks)
    rows,hooks=mode('hook')
    assert 'walter-intake' not in rows and 'walter-events' not in rows and 'walter-owner-turn' in rows
    assert {'UserPromptSubmit','Stop'}<=set(hooks)
    v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']={'intake':'both'}
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
    with pytest.raises(ValueError,match='intake'):c.install('dsh',home)
    assert e1[1]==(home/'walter-hooks.json').read_bytes()
    norm=lambda text:sorted(json.dumps(r,sort_keys=True) for r in c._dsh_yaml(text))   # same rows (order may move)
    assert norm(e1[0].decode())==norm((home/'cordis.patch.yml').read_text())
