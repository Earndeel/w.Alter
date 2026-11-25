"""DSH composition — rollback suite (moved out of core/tests on 2026-11-25).

DSH was uninstalled on 2026-11-18 (Monsieur validated the native engine; `/user/Lucas/backups/changes/2026-11-18-dsh-retrait`).
Its composition code stays in `walter_platform/composition.py` for the rollback only (components `engine-compositions`,
`engine-plugins`, `engine-api`, `dsh-hooks`, `dsh-web-ui` = `obsolete`). These tests check that code; they need the
DSH installation (`/opt/dsh`), so the active suite (`walter-core-test`, `tests/`) no longer collects them and this
module skips itself while DSH is absent. After a rollback restore, run:
    walter-core-test -q engine/compositions/tests/
The native engine's own equivalents (web sign-in secret never shown, cookies, panels) are tested in
`engine/tests/test_native_engine.py` and `interfaces/web/panels/tests/`."""
import copy
import json,os,sys
from pathlib import Path
import pytest
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from walter_platform import composition as c
from walter_platform import harness_transaction as tx

DSH_LIB=Path('/opt/dsh/node_modules/@deepseek-ai')
pytestmark=pytest.mark.skipif(not DSH_LIB.exists(),reason='DSH uninstalled 2026-11-18: rollback suite, runs once DSH is restored')

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

@pytest.mark.parametrize('host',['dsh'])
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

def test_disabled_dsh_plugin_overlay_is_not_bypassed(home):
    p=home/'cordis.patch.yml';p.write_text('- id: hooks-walter\n  disabled: true\n')
    with pytest.raises(ValueError,match='separate override'):c.install('dsh',home,apply=True)

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


def test_engine_policy_switch_enforce_first_and_off_restores(home,monkeypatch):
    """Lot E3 (2026-11-10): `policy = "enforce"` puts Walter's policy plugin first among the engine rows, with or
    without the native intake; `off` (the neutral default) gives back the composition byte for byte."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    before=(home/'cordis.patch.yml').read_text()
    values=c.engine_values()
    def compose(engine):
        v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']=engine
        monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
        c.install('dsh',home,apply=True,backup_root=home.parent/'b')
        assert not c.install('dsh',home)['changed']
        d=c._dsh_yaml((home/'cordis.patch.yml').read_text())
        return [e['id'] for r in d for e in r.get('insert',[]) if e['id'] in c.ENGINE_ROWS],{e['id']:e for r in d for e in r.get('insert',[])}
    ids,rows=compose({'intake':'hook','policy':'enforce'})
    assert ids==['walter-policy','walter-budget'] and rows['walter-policy']['name'].endswith('engine/plugins/policy/index.mjs')
    assert rows['walter-policy']['config']['interface']=='web' and 'state/core/security' in rows['walter-policy']['config']['stateDir']
    ids,_=compose({'intake':'native','policy':'enforce'})
    assert ids==['walter-policy','walter-budget','walter-intake','walter-events']
    compose({'intake':'hook','policy':'off'})
    norm=lambda text:sorted(json.dumps(r,sort_keys=True) for r in c._dsh_yaml(text))
    assert norm(before)==norm((home/'cordis.patch.yml').read_text())
    v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']={'policy':'maybe'}
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
    with pytest.raises(ValueError,match='policy'):c.install('dsh',home)


def test_engine_api_switch_web_profile_only_and_off_removes(home,monkeypatch):
    """Lot E4 (2026-11-10): `api = "on"` adds the Engine API plugin to the web profile only (never a headless run),
    before the dsh-web block, with instance locations; `off` (default) removes it and gives the profile back."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    web=home/'profiles'/'web'/'cordis.patch.yml'
    before=web.read_text() if web.exists() else ''
    values=c.engine_values()
    def compose(engine):
        v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']=engine
        monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
        c.install('dsh',home,apply=True,backup_root=home.parent/'b')
        assert not c.install('dsh',home)['changed']
        return web.read_text() if web.exists() else ''
    text=compose({'api':'on','api_port':8899})
    if not before:pytest.skip('no web profile composed in this environment')
    rows={e['id']:e for r in c._dsh_yaml(text) for e in r.get('insert',[])}
    api=rows['walter-engine-api']
    assert api['name'].endswith('interfaces/api/index.mjs') and api['config']['port']==8899
    assert 'state/core/engine/api' in api['config']['stateDir'] and api['config']['tokenFile'].endswith('bootstrap/engine/api.token')
    assert text.index('# walter:dsh-api ')<text.index('# walter:dsh-web ')
    assert 'walter-engine-api' not in (home/'cordis.patch.yml').read_text()
    hl=home/'profiles'/'headless'/'cordis.patch.yml'
    assert not hl.exists() or 'walter-engine-api' not in hl.read_text()
    monkeypatch.setenv('WALTER_ENGINE_API_STATE',str(home.parent/'api-state'))
    text=compose({'api':'on'})
    api={e['id']:e for r in c._dsh_yaml(text) for e in r.get('insert',[])}['walter-engine-api']
    assert api['config']['stateDir']==str(home.parent/'api-state') and api['config']['port']==8895
    monkeypatch.delenv('WALTER_ENGINE_API_STATE')
    assert compose({'api':'off'})==before
    v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']={'api':'maybe'}
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
    with pytest.raises(ValueError,match='api'):c.install('dsh',home)


def test_engine_subagents_switch_keeps_spawn_only_with_depth_and_off_restores(home,monkeypatch):
    """Lot E5 (2026-11-10): `subagents = "on"` gives back the kernel's in-process sub-agents (runtime + spawn tool +
    control/list), depth ≤ SUBAGENT_MAX_DEPTH; fork, workflows, Ralph and Codex/Claude Code children stay off.
    `off` (default) gives the composition back exactly."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'b')
    root=home/'cordis.patch.yml';web=home/'profiles'/'web'/'cordis.patch.yml'
    before=(root.read_text(),web.read_text() if web.exists() else '')
    values=c.engine_values()
    def compose(engine):
        v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']=engine
        monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
        c.install('dsh',home,apply=True,backup_root=home.parent/'b')
        assert not c.install('dsh',home)['changed']
        return root.read_text(),web.read_text() if web.exists() else ''
    r,w=compose({'subagents':'on'})
    if not before[1]:pytest.skip('no web profile composed in this environment')
    off={e['id'] for e in c._dsh_yaml(r) if isinstance(e,dict) and e.get('disabled')}
    assert not off & set(c.SUBAGENT_KEEP) and {'subagent-fork-in-process','tool-subagent-fork','tool-workflow','goal'}<=off
    wrows=c._dsh_yaml(w)
    woff={e['id'] for e in wrows if isinstance(e,dict) and e.get('disabled')}
    assert not woff & set(c.SUBAGENT_KEEP) and 'tool-ralph' in woff
    preset=[e for e in wrows if isinstance(e,dict) and e.get('id')=='preset-standard'][0]
    def flat(es):
        for e in es:
            yield e
            if e.get('group'):yield from flat(e.get('config') or [])
    ids={e['id']:e for e in flat(preset['config']['plugins'])}
    assert ids['tool-subagent']['config']['maxDepth']==c.SUBAGENT_MAX_DEPTH and ids['tool-subagent']['config']['provider']=='spawn' and ids['tool-subagent']['config']['backgroundMode']=='one-shot'
    assert not {'tool-subagent-fork','tool-subagent-codex','tool-subagent-claude-code','workflow-ptc','tool-workflow','tool-ralph'}&set(ids)
    r,w=compose({'subagents':'off'})   # root re-dumped: same rows (disabled rows re-appended, order irrelevant)
    rows=lambda t:sorted(json.dumps(e,sort_keys=True,default=str) for e in c._dsh_yaml(t))
    assert w==before[1] and rows(r)==rows(before[0])
    v=copy.deepcopy(values);v.setdefault('dsh',{})['engine']={'subagents':'all'}
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(v))
    with pytest.raises(ValueError,match='subagents'):c.install('dsh',home)


def test_web_sign_in_link_never_printed(monkeypatch,tmp_path):
    # owner, 2026-11-11: the launch token must not reach the journal; the link goes to a root-only instance file
    monkeypatch.setenv('WALTER_ENGINE_WEB_LOGIN',str(tmp_path/'login-url'))
    rows=yaml.load(c._dsh_web_profile(4000).replace('!!js ','js:'),Loader=yaml.SafeLoader)
    web=[r for r in rows if r.get('id')=='web-runtime'][0]
    assert web['config']['printUrl'] is False
    login=[e for r in rows for e in r.get('insert',[]) if e.get('id')=='walter-web-login'][0]
    assert login['name'].endswith('interfaces/web/login-link.mjs') and login['config']['file']==str(tmp_path/'login-url')


def test_dsh_panels_rendered_from_engine_values_and_dropped_when_none(home,monkeypatch):
    """Panels of the web interface (pages of other modules in its sidebar) come from engine.toml [[dsh.web.panels]]."""
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    assert '# walter:dsh-panels ' not in _web(home)
    values=c.engine_values()
    values['dsh']['web']['panels']=[{'id':'board','label':'Développement','path':'/board','upstream':'http://127.0.0.1:9'}]
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(values))
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    text=_web(home)
    assert text.count('# walter:dsh-panels ')==1 and text.index('# walter:dsh-panels ')<text.index('# walter:dsh-web ')
    [row]=[r for r in c._dsh_yaml(text) if any(e.get('id')=='walter-web-panels' for e in r.get('insert',[]))]
    entry=row['insert'][0]
    assert entry['name'].endswith('/interfaces/web/panels/index.mjs')
    assert entry['config']=={'panels':[{'id':'board','label':'Développement','path':'/board','upstream':'http://127.0.0.1:9'}]}
    assert not c.install('dsh',home)['changed']
    values['dsh']['web']['panels']=[]
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    assert '# walter:dsh-panels ' not in _web(home)


def test_dsh_settings_links_rendered_alone_and_checked(home,monkeypatch):
    """Settings links (rows of Settings › General opening a page in a new tab) come from engine.toml [[dsh.web.links]]."""
    values=c.engine_values()
    values['dsh']['web']['panels']=[]
    values['dsh']['web']['links']=[{'id':'library','label':'Bibliothèque','description':'Modèles actifs','url':'https://lib.example/fr/'}]
    monkeypatch.setattr(c,'engine_values',lambda instance=True:copy.deepcopy(values))
    c.install('dsh',home,apply=True,backup_root=home.parent/'backups')
    [row]=[r for r in c._dsh_yaml(_web(home)) if any(e.get('id')=='walter-web-panels' for e in r.get('insert',[]))]
    assert row['insert'][0]['config']=={'links':[{'id':'library','label':'Bibliothèque','description':'Modèles actifs','url':'https://lib.example/fr/'}]}
    values['dsh']['web']['links']=[{'id':'library','label':'Bibliothèque','url':'https://lib.example/fr/','section':'models','section_label':'Modèles'}]
    assert yaml.safe_load(c._dsh_panels(values))[0]['insert'][0]['config']['links'][0]['section']=='models'
    for bad in ({'id':'x','label':'X','url':'http://lib.example/'},{'id':'x','label':'X','url':'javascript:alert(1)'},{'id':'x','url':'https://a.b/'},
                {'id':'x','label':'X','url':'https://a.b/','section':'general'},{'id':'x','label':'X','url':'https://a.b/','section':'Bad'}):
        values['dsh']['web']['links']=[bad]
        with pytest.raises(ValueError,match='dsh.web.links'):c._dsh_panels(values)


def test_dsh_panels_bad_values_fail(home):
    for bad in ({'id':'board','label':'B','path':'board','upstream':'http://h'},
                {'id':'board','label':'B','path':'/board','upstream':'file:///etc'},
                {'id':'board','path':'/board','upstream':'http://h'}):
        with pytest.raises(ValueError,match='panels'):c._dsh_panels({'dsh':{'web':{'panels':[bad]}}})


def test_dsh_panels_actions_passed_and_checked(home):
    """A panel may declare action prefixes (POSTs relayed, e.g. the board's buttons); anything else is refused."""
    ok={'id':'board','label':'D','path':'/board','upstream':'http://127.0.0.1:9','actions':['/api/actions/']}
    text=c._dsh_panels({'dsh':{'web':{'panels':[ok]}}})
    [row]=[r for r in c._dsh_yaml(text) if any(e.get('id')=='walter-web-panels' for e in r.get('insert',[]))]
    assert row['insert'][0]['config']['panels'][0]['actions']==['/api/actions/']
    for bad in (['api/actions'],['/api/../x/'],'/api/actions/'):
        with pytest.raises(ValueError,match='panels'):c._dsh_panels({'dsh':{'web':{'panels':[{**ok,'actions':bad}]}}})
