import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from walter_context import capabilities
from walter_context.bridge import dispatch

TOOLS = ['walter_route','walter_run','walter_decide','walter_plans']


def note(content='Trusted usage note'):
    return {'schema_version':1,'note_version':1,'id':'walter-router.usage','module':'router','format':'text/markdown',
            'placement':'stable_capabilities','refresh':'next_owner_message','content':content,'chars':len(content),
            'sha256':hashlib.sha256(content.encode()).hexdigest(),'required_tools':TOOLS}


@pytest.fixture
def source(monkeypatch):
    state={'note':note(),'calls':0}
    def command(args,**kwargs):
        assert args == ['walter-router','brief','--json']
        state['calls']+=1
        return SimpleNamespace(returncode=0,stdout=json.dumps(state['note']))
    monkeypatch.setattr(capabilities.subprocess,'run',command)
    return state


def test_available_tools_enable_the_verified_note(source):
    out=capabilities.router_note(TOOLS)
    assert out['status']=='ready' and out['injection_allowed'] and out['content']==source['note']['content']


@pytest.mark.parametrize('tools',[None,[],['walter_run']])
def test_missing_tool_inventory_never_claims_a_capability(source,tools):
    out=capabilities.router_note(tools)
    assert not out['injection_allowed'] and out['content'] is None


@pytest.mark.parametrize('field,value',[('schema_version',2),('sha256','bad'),('chars',0),('module','unknown'),
                                       ('placement','user'),('required_tools',[])])
def test_invalid_producer_metadata_is_rejected(source,field,value):
    source['note'][field]=value
    out=capabilities.router_note(TOOLS)
    assert out['status']=='invalid' and not out['injection_allowed'] and 'content' not in out


def test_note_is_frozen_for_an_owner_turn_and_updates_for_the_next(source):
    session=capabilities.TurnNotes()
    first=session.prepare('turn-a',TOOLS)
    source['note']=note('New usage guidance')
    first['content']='caller cannot alter the cached snapshot'
    assert session.prepare('turn-a',TOOLS)['content']=='Trusted usage note'
    assert source['calls']==1
    assert session.prepare('turn-b',TOOLS)['content']=='New usage guidance'
    assert source['calls']==2


def test_tool_revocation_disables_injection_even_with_a_cached_note(source):
    session=capabilities.TurnNotes()
    assert session.prepare('a',TOOLS)['injection_allowed']
    out=session.prepare('a',[])
    assert not out['injection_allowed'] and out['content'] is None and source['calls']==1


def test_source_failure_is_explicit_and_contains_no_raw_diagnostic(monkeypatch):
    monkeypatch.setattr(capabilities.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='private diagnostic'))
    out=capabilities.router_note(TOOLS)
    assert out['status']=='unavailable' and 'private' not in json.dumps(out)


def test_bridge_accepts_a_note_without_a_message_history(source):
    out=dispatch({'version':1,'op':'capability','module':'router','available_tools':TOOLS})
    assert out['version']==1 and out['engine']=='walter-context' and out['injection_allowed']


def test_oversized_note_is_rejected(source):
    source['note']=note('x'*6001)
    assert capabilities.router_note(TOOLS)['status']=='invalid'


# ---- module layer ----------------------------------------------------------------------------------------------

def mnote(module, content, tools):
    return {'schema_version':1,'note_version':1,'id':f'walter-{module}.brief','module':module,'format':'text/markdown',
            'placement':'stable_capabilities','refresh':'next_owner_message','content':content,'chars':len(content),
            'sha256':hashlib.sha256(content.encode()).hexdigest(),'required_tools':tools}


@pytest.fixture
def modules(monkeypatch):
    state={'notes':[mnote('memory','### Memory\nuse memory_context',['memory_context']),
                    mnote('router','## Walter Router\nuse walter_run',['walter_run']),
                    mnote('skills','### Skills\nuse skills_search',['skills_search'])],'calls':0,'problems':[]}
    def command(args,**kwargs):
        assert args[:5] == ['walter','present','notes','--form',args[4]]
        state['calls']+=1; state['args']=args
        notes=state['notes'] if args[4]=='full' else [
            {**mnote(n['module'],f"- **{n['module']}** — line",n['required_tools']),'id':f"walter-{n['module']}.summary",'level':'M0'}
            for n in state['notes']] + [n for n in state['notes'] if n['module'] in args[6::2]]
        return SimpleNamespace(returncode=0,stdout=json.dumps({'schema_version':1,'notes':notes,
                                                               'problems':state['problems']}))
    monkeypatch.setattr(capabilities.subprocess,'run',command)
    return state

ALL=['memory_context','walter_run','skills_search','module_guide','module_index']


def test_layer_composes_every_module_in_order_with_the_navigation_header(modules):
    out=capabilities.compose(ALL)
    assert out['status']=='ready' and out['injection_allowed']
    assert out['content'].startswith('## Modules W.Alter\n') and 'module_guide(module)' in out['content']
    c=out['content']
    assert c.index('### Memory') < c.index('### Walter Router') < c.index('### Skills')  # router heading demoted
    assert out['sha256']==hashlib.sha256(c.encode()).hexdigest() and out['chars']==len(c)


def test_a_module_whose_tools_are_absent_is_left_out_not_claimed(modules):
    out=capabilities.compose(['memory_context','skills_search'])
    assert 'Walter Router' not in out['content'] and 'module_guide' not in out['content']
    assert {'id':'walter-router.brief','status':'missing_tools','missing_tools':['walter_run']} in out['skipped']


def test_no_inventory_injects_nothing(modules):
    out=capabilities.compose(None)
    assert not out['injection_allowed'] and out['content'] is None


def test_an_invalid_module_note_is_dropped_and_the_others_kept(modules):
    modules['notes'][0]['sha256']='bad'
    out=capabilities.compose(ALL)
    assert '### Memory' not in out['content'] and '### Skills' in out['content']


def test_layer_budget_is_respected(modules, monkeypatch):
    real=capabilities.capability_settings
    monkeypatch.setattr(capabilities,'capability_settings',lambda: {**real(),'layer_max_chars':len(capabilities.HEADER)+40})
    out=capabilities.compose(ALL)
    assert out['chars']<=len(capabilities.HEADER)+40 and any(s['status']=='over_budget' for s in out['skipped'])


def test_layer_is_frozen_for_an_owner_turn(modules):
    layer=capabilities.TurnLayer()
    first=layer.prepare('t1',ALL)['content']
    modules['notes'][2]=mnote('skills','### Skills\nnew map',['skills_search'])
    assert layer.prepare('t1',ALL)['content']==first and modules['calls']==1
    assert 'new map' in layer.prepare('t2',ALL)['content']


def test_source_failure_is_explicit(monkeypatch):
    monkeypatch.setattr(capabilities.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='private'))
    out=capabilities.compose(ALL)
    assert out['status']=='unavailable' and not out['injection_allowed'] and 'private' not in json.dumps(out)


def test_bridge_composes_the_layer(modules):
    out=dispatch({'version':1,'op':'capability','module':'all','available_tools':ALL})
    assert out['injection_allowed'] and out['id']=='walter-modules.layer'


def test_m0_form_lists_every_module_in_one_line_and_m1_only_for_the_plan(modules):
    out=capabilities.compose(ALL,'m0',['skills'])
    c=out['content']
    assert out['form']=='m0' and capabilities.M0_TITLE in c
    assert '- **memory** — line' in c and '- **router** — line' in c and '- **skills** — line' in c
    assert '### Skills' in c and '### Memory' not in c and 'Walter Router' not in c
    assert modules['args'][-2:]==['--m1','skills']
    assert [m['level'] for m in out['modules']].count('M0')==3


def test_default_form_is_unchanged(modules):
    out=capabilities.compose(ALL)
    assert out['form']=='full' and capabilities.M0_TITLE not in out['content'] and '### Memory' in out['content']
