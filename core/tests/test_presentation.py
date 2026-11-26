import json
from types import SimpleNamespace

import pytest

from walter_platform import contracts, presentation

BASE = {'audience': 'agent', 'title': 'Demo', 'tools': ['demo_tool'], 'summary': 'manifest/SUMMARY.md',
        'manifest': 'manifest/MANIFEST.md',
        'guide': 'manifest/GUIDE.md'}


@pytest.mark.parametrize('bad', [{**BASE, 'audience': 'world'}, {**BASE, 'brief': 'text in the contract'},
                                 {k: v for k, v in BASE.items() if k != 'manifest'},
                                 {**BASE, 'tools': ['Bad Tool']}, {**BASE, 'index': {'command': []}},
                                 {**BASE, 'manifest': '../escape.md'}, {**BASE, 'manifest_command': []}])
def test_invalid_presentation_is_refused(bad):
    with pytest.raises(ValueError):
        contracts._presentation(bad, contracts.contract_path)


def test_texts_are_files_of_the_module_folder():
    contracts._presentation({**BASE, 'index': {'command': ['demo', 'index'], 'section_arg': '--s', 'paged': True}},
                            contracts.contract_path)
    out = contracts.expand({'id': 'demo', 'presentation': dict(BASE), 'contract': {}}, '/walter/demo', '/walter/demo')
    assert out['presentation']['manifest'] == '/walter/demo/manifest/MANIFEST.md'
    assert out['presentation']['guide'] == '/walter/demo/manifest/GUIDE.md'


@pytest.fixture
def registry(monkeypatch, tmp_path):
    (tmp_path / 'MANIFEST.md').write_text('# Demo\n\nWhat it is.\n\n## Use\nCall demo_tool.\n')
    (tmp_path / 'GUIDE.md').write_text('# Demo guide\n')
    (tmp_path / 'SUMMARY.md').write_text('Does demo things with `demo_tool`.\n')
    rows = [{'id': 'demo', 'presentation': {**BASE, 'manifest': str(tmp_path / 'MANIFEST.md'),
                                             'summary': str(tmp_path / 'SUMMARY.md'),
                                             'guide': str(tmp_path / 'GUIDE.md'),
                                             'index': {'command': ['demo', 'list']}}},
            {'id': 'hidden', 'presentation': {**BASE, 'audience': 'internal'}}, {'id': 'plain'}]
    monkeypatch.setattr(presentation.registry, 'load', lambda: {'modules': rows})
    return rows


def test_level_one_is_the_manifest_file_demoted_under_the_layer(registry):
    doc = presentation.notes()
    assert [n['module'] for n in doc['notes']] == ['demo'] and not doc['problems']
    n = doc['notes'][0]
    assert n['content'].startswith('### Demo\n') and '#### Use' in n['content'] and n['chars'] == len(n['content'])
    assert n['required_tools'] == ['demo_tool'] and n['placement'] == 'stable_capabilities'


def test_live_part_is_appended(registry, monkeypatch):
    registry[0]['presentation']['manifest_command'] = ['demo', 'live']
    monkeypatch.setattr(presentation.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps({'content': '## Live\nnow'})))
    text = presentation.manifest('demo')
    assert text.index('What it is.') < text.index('### Live')


def test_oversized_level_one_is_refused(registry, tmp_path):
    (tmp_path / 'MANIFEST.md').write_text('# Demo\n' + 'x' * 3100)
    doc = presentation.notes()
    assert doc['notes'] == [] and doc['problems'][0]['module'] == 'demo'


def test_guide_and_unpaged_list_index(registry, monkeypatch):
    assert presentation.guide('demo') == '# Demo guide\n'
    monkeypatch.setattr(presentation.subprocess, 'run',
                        lambda args, **k: SimpleNamespace(returncode=0, stdout=json.dumps(list(range(30)))))
    page = presentation.index('demo', offset=20, limit=20)['index']
    assert page['entries'] == list(range(20, 30)) and page['next_offset'] is None and page['total'] == 30
    with pytest.raises(ValueError):
        presentation.index('demo', section='x')


def test_failing_live_part_is_reported_not_hidden(registry, monkeypatch):
    registry[0]['presentation']['manifest_command'] = ['demo', 'live']
    monkeypatch.setattr(presentation.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=''))
    doc = presentation.notes()
    assert doc['notes'] == [] and doc['problems'][0]['module'] == 'demo'


def test_m0_form_gives_one_line_per_module_and_m1_only_for_the_selection(registry):
    doc = presentation.notes('m0')
    assert [(n['module'], n['level']) for n in doc['notes']] == [('demo', 'M0')]
    assert doc['notes'][0]['content'] == '- `demo` — Does demo things with `demo_tool`.'
    assert doc['notes'][0]['id'] == 'walter-demo.summary'
    doc = presentation.notes('m0', ['demo', 'ghost'])
    assert [n['level'] for n in doc['notes']] == ['M0', 'M1'] and doc['m1'] == ['demo']
    assert doc['problems'] == [{'module': 'ghost', 'level': 'M1', 'error': 'UnknownModule'}]
    assert [n['level'] for n in presentation.notes()['notes']] == ['M1']  # default unchanged


def test_m0_must_stay_one_short_line(registry, tmp_path):
    (tmp_path / 'SUMMARY.md').write_text('x' * (presentation.SUMMARY_MAX + 1))
    assert presentation.notes('m0')['problems'][0]['level'] == 'M0'
    with pytest.raises(ValueError):
        presentation.notes('compact')


def test_walter_check_fails_on_a_presentation_injection_would_reject(registry, tmp_path):
    """2026-11-14: the Router's and ops' M0 lines (274 / 223 chars) were dropped at injection for three days, silently."""
    from walter_platform import registry as reg
    assert reg._presentation_check() == {'ok': True, 'problems': []}
    (tmp_path / 'SUMMARY.md').write_text('x' * (presentation.SUMMARY_MAX + 1) + '\n')
    out = reg._presentation_check()
    assert not out['ok'] and out['problems'][0]['module'] == 'demo' and out['problems'][0]['level'] == 'M0'


# ── D1/D2/D3 for W.Alter, its modules and their components (lot 3c, 2026-11-24) ──
@pytest.fixture
def tree(registry, monkeypatch, tmp_path):
    docs = tmp_path / 'walter-docs'
    docs.mkdir()
    (docs / 'SUMMARY.md').write_text('W.Alter is a demo intelligence.\n')
    (docs / 'MANIFEST.md').write_text('# W.Alter\n\nHow it is built.\n')
    (docs / 'GUIDE.md').write_text('# W.Alter guide\n')
    monkeypatch.setattr(presentation, '_walter_file', lambda name: docs / name)
    readme = tmp_path / 'part.md'
    readme.write_text('# Part\n\n| **Role** | does a part |\n|---|---|\n\nBody of the part.\n')
    registry[0].update(root=str(tmp_path), anchors=['contracts/demo.json'], contract={'purpose': 'Demo purpose'},
                       components=[{'id': 'part', 'role': 'One part of the demo', 'status': 'active',
                                    'path': 'part.py', 'readme': str(readme), 'data': ['postgres:demo']},
                                   {'id': 'old', 'role': 'An old part', 'status': 'obsolete'},
                                   {'id': 'next', 'role': 'A planned part', 'status': 'planned'}])
    (tmp_path / 'README.md').write_text('# Demo README\n')
    return tmp_path


def test_d1_identifies_the_entity_and_says_how_to_open_d2(tree):
    assert presentation.d1('walter') == 'W.Alter is a demo intelligence. D2: `module_guide("walter", depth="D2")`.'
    assert presentation.d1('demo').startswith('Does demo things with `demo_tool`. D2: `module_guide("demo"')
    assert presentation.d1('demo/part') == 'One part of the demo. D2: `module_guide("demo/part", depth="D2")`.'
    with pytest.raises(ValueError, match='Its components: part, old, next'):
        presentation.resolve('demo/ghost')
    with pytest.raises(ValueError, match='Modules: demo'):
        presentation.resolve('ghost')
    with pytest.raises(ValueError, match='Components with that name: demo/part'):
        presentation.resolve('part/x')


def test_d2_lists_children_at_d1_and_d3_gives_detail_and_sources(tree):
    walter = presentation.d2('walter')
    assert walter.startswith('# W.Alter') and '- `demo` — Does demo things' in walter and '`hidden`' not in walter
    module = presentation.d2('demo')
    assert 'What it is.' in module and '- `demo/part` — One part of the demo.' in module
    assert '- `demo/next` — A planned part. (planned)' in module and '`demo/old`' not in module
    assert '1 obsolete component(s)' in module
    card = presentation.d2('demo/part')
    assert '**Role.** One part of the demo.' in card and '`postgres:demo`' in card and '| **Role** |' in card
    assert 'Body of the part.' not in card
    assert 'Body of the part.' in presentation.d3('demo/part')
    d3 = presentation.d3('demo')
    assert d3.startswith('# Demo guide') and '## Sources' in d3 and 'Demo purpose' in d3
    assert presentation.document('walter', 'd3') == '# W.Alter guide\n'
    with pytest.raises(ValueError):
        presentation.document('demo', 'D4')


def test_socle_carries_walter_d1_and_in_s2_every_module_d1(tree):
    s1, s2 = presentation.socle('s1'), presentation.socle('s2')
    assert s1.startswith('## W.Alter\nW.Alter is a demo intelligence.') and 'module_guide(path, depth)' in s1
    assert 'module_guide("walter", depth="D2")' in s1 and '### Modules' not in s1
    assert '### Modules (D1)\n- `demo` — Does demo things' in s2
    with pytest.raises(ValueError):
        presentation.socle('s3')


def test_notes_can_carry_walter_d2_for_a_message_about_walter(tree):
    """Lot 3d (2026-11-24): the plan's domain "walter" asks for W.Alter's own D2 through the same notes call."""
    out = presentation.notes('m0', ['walter', 'demo'])
    first = out['notes'][0]
    assert first['module'] == 'walter' and first['level'] == 'M1' and first['id'].endswith('.manifest')
    assert first['content'].startswith('### W.Alter') and '- `demo` — Does demo things' in first['content']
    assert out['m1'] == ['demo', 'walter'] and not out['problems']
    assert all(n['module'] != 'walter' for n in presentation.notes('m0', ['demo'])['notes'])
