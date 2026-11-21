from walter_skills import domains, store
from contextlib import nullcontext
from types import SimpleNamespace


def test_index_explains_each_active_entry_without_loading_procedures(tmp_path, monkeypatch):
    for domain, name, desc in [('video', 'ad-workflow', 'Use when making an ad from a reference.'),
                               ('video', 'render-video', 'Use when rendering the selected shots.')]:
        d = tmp_path / 'skills' / domain / name
        d.mkdir(parents=True)
        (d / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: {desc}\n---\nSECRET_BODY_NOT_FOR_INDEX\n')
    store.write_sidecar(tmp_path / 'skills/video/ad-workflow', {'kind': 'workflow', 'requires': ['render-video']})
    archived = tmp_path / 'archive/retired-video'
    archived.mkdir(parents=True)
    (archived / 'SKILL.md').write_text('---\nname: retired-video\ndescription: Old\n---\n')
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    states = {}
    monkeypatch.setattr(domains.registry, 'set_state', lambda k,v: states.__setitem__(k,v))
    monkeypatch.setattr(domains.registry, 'get_state', lambda k,default=None: states.get(k,default))
    monkeypatch.setattr(domains.registry, 'cards', lambda: {})
    monkeypatch.setattr(domains.registry, 'db', lambda: nullcontext(SimpleNamespace(execute=lambda *a: [])))
    monkeypatch.setattr(domains.registry, 'ranker', lambda: None)
    index = domains.build()
    assert index[0].get('entries'), 'domain map lacks an index of what each procedure does'
    overview = domains.render('skills_search')
    assert 'ad-workflow' not in overview and 'SECRET_BODY_NOT_FOR_INDEX' not in overview
    entries = domains.index('video')['entries']
    assert [e['name'] for e in entries] == ['ad-workflow', 'render-video']
    assert entries[0]['kind'] == 'workflow' and entries[0]['requires'] == ['render-video']
    assert 'reference' in entries[0]['purpose']
    assert 'SECRET_BODY_NOT_FOR_INDEX' not in str(entries)
    # Editing/archiving is reflected by the next curator publication.
    (tmp_path / 'skills/video/render-video/SKILL.md').unlink()
    domains.build()
    assert [e['name'] for e in domains.index('video')['entries']] == ['ad-workflow']


def test_discovery_is_available_through_http_and_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from walter_skills import api, client
    monkeypatch.setattr(domains, 'manifest', lambda: 'Module purpose and components')
    monkeypatch.setattr(domains, '_load', lambda root=None: [
        {'domain': 'video', 'count': 1, 'workflows': 1, 'entries': [
            {'name': 'ad-workflow', 'kind': 'workflow', 'purpose': 'Make an ad', 'requires': ['render']}]}])
    http = TestClient(api.app)  # no lifespan: engine warmup is unnecessary for discovery
    response = http.get('/v1/index', params={'domain': 'video'})
    assert response.status_code == 200
    assert response.json()['entries'][0]['name'] == 'ad-workflow'
    assert http.get('/v1/manifest').text == 'Module purpose and components'
    def call(method, path, body=None, timeout=4):
        r = http.request(method, path, json=body)
        r.raise_for_status()
        return r.json() if r.headers.get('content-type', '').startswith('application/json') else r.text
    monkeypatch.setattr(client, '_call', call)
    assert client.index('video')['total'] == 1
    assert client.manifest() == 'Module purpose and components'


def test_curator_publishes_an_index_of_its_final_active_library(tmp_path, monkeypatch):
    from walter_skills import curation
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(domains.registry, 'cards', lambda: {})
    monkeypatch.setattr(domains.registry, 'get_state', lambda *a: None)
    monkeypatch.setattr(domains.registry, 'set_state', lambda *a: None)
    monkeypatch.setattr(domains.registry, 'ledger', lambda *a, **kw: None)
    monkeypatch.setattr(curation, 'REPORTS', tmp_path / 'reports')
    for name, value in [('usage', {}), ('judged_needed', {}), ('pinned', set()),
                        ('recently_curated', set()), ('successors', {})]:
        monkeypatch.setattr(curation.signals, name, lambda *a, value=value: value)
    monkeypatch.setattr(curation.signals, 'similarity', lambda *a: None)
    monkeypatch.setattr(curation.Encoder, 'get', lambda: None)
    d = tmp_path / 'skills/video/new-video'
    d.mkdir(parents=True)
    (d / 'SKILL.md').write_text('---\nname: new-video\ndescription: Use when rendering a video.\n---\nBody\n')
    curation.run(apply=True, use_models=False, only={'drafts'})
    assert (tmp_path / '.cache/library-index.json').exists(), 'Curator did not publish its discovery index'
    assert domains.index('video')['entries'][0]['name'] == 'new-video'
