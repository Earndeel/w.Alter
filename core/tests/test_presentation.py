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
    assert doc['notes'][0]['content'] == '- **Demo** — Does demo things with `demo_tool`.'
    assert doc['notes'][0]['id'] == 'walter-demo.summary'
    doc = presentation.notes('m0', ['demo', 'ghost'])
    assert [n['level'] for n in doc['notes']] == ['M0', 'M1'] and doc['m1'] == ['demo']
    assert doc['problems'] == [{'module': 'ghost', 'level': 'M1', 'error': 'UnknownModule'}]
    assert [n['level'] for n in presentation.notes()['notes']] == ['M1']  # default unchanged


def test_m0_must_stay_one_short_line(registry, tmp_path):
    (tmp_path / 'SUMMARY.md').write_text('x' * 201)
    assert presentation.notes('m0')['problems'][0]['level'] == 'M0'
    with pytest.raises(ValueError):
        presentation.notes('compact')


def test_walter_check_fails_on_a_presentation_injection_would_reject(registry, tmp_path):
    """2026-11-14: the Router's and ops' M0 lines (274 / 223 chars) were dropped at injection for three days, silently."""
    from walter_platform import registry as reg
    assert reg._presentation_check() == {'ok': True, 'problems': []}
    (tmp_path / 'SUMMARY.md').write_text('x' * 201 + '\n')
    out = reg._presentation_check()
    assert not out['ok'] and out['problems'][0]['module'] == 'demo' and out['problems'][0]['level'] == 'M0'
