"""Regressions from AA's November public page-data and leaderboard redesign."""
import gzip
import hashlib
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from walter_router.analysis.parse import parse_benchmarks
from walter_router.research.benchmarks import aa, aa_data, aa_evaluations, aa_media


def flight(value, split=False):
    text = 'a1:' + json.dumps(value)
    chunks = [text[:len(text)//2], text[len(text)//2:]] if split else [text]
    return ''.join('<script>self.__next_f.push([1,' + json.dumps(chunk) + '])</script>' for chunk in chunks)


def encrypted(value):
    key = bytes(range(32))
    raw = AESGCM(key).encrypt(hashlib.sha256(key).digest()[:12], gzip.compress(json.dumps(value).encode()), None)
    return {'path': '/data/catalogue.txt', 'key': key.hex()}, raw


def test_full_manifest_preserves_exact_variant_scores_and_costs(monkeypatch):
    models = [{'slug': f'm-{i}', 'intelligenceIndex': 40+i/1000, 'gpqa': 0.8,
               'intelligenceIndexCostPerTask': {'cost': {'total': 0.25}}} for i in range(300)]
    manifest, raw = encrypted({'models': models})
    calls = []
    monkeypatch.setattr(aa_data, 'fetch_data', lambda path: calls.append(path) or raw)
    page = flight({'manifest': {'path': '/data/host-endpoints.txt'}, 'children': {
        'initialModels': models[:28], 'manifest': manifest}}, split=True)
    full = aa_data.catalogue_models(page)
    assert len(full) == 300 and calls == ['/data/catalogue.txt']
    rows = aa.records(full)
    assert rows[299]['slug'] == 'm-299'
    assert rows[299]['intelligence_index'] == models[299]['intelligenceIndex']
    assert rows[299]['aa_cost_per_task_intelligence_usd'] == 0.25
    evaluations = aa_evaluations.merge(full)
    assert len(evaluations) == 300 and evaluations['m-299']['gpqa'] == 0.8


def test_manifest_integrity_failure_never_falls_back_to_chart_preview(monkeypatch):
    manifest, raw = encrypted({'models': [{'slug': f'm-{i}'} for i in range(300)]})
    monkeypatch.setattr(aa_data, 'fetch_data', lambda path: raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        aa_data.catalogue_models(flight({'initialModels': [{'slug': 'preview'}], 'manifest': manifest}))


@pytest.mark.parametrize('models', [[{'slug': 'preview'}], [{'slug': None}]*300, {'wrong': []}])
def test_incomplete_or_unidentified_catalogue_is_rejected(monkeypatch, models):
    monkeypatch.setattr(aa_data, 'manifest_data', lambda manifest: {'models': models})
    with pytest.raises(ValueError, match='partial chart|slugs'):
        aa_data.catalogue_models(flight({'initialModels': [{'slug': 'preview'}],
                                        'manifest': {'path': '/data/catalogue.txt'}}))


def test_missing_variant_slug_never_reaches_ingestion():
    with pytest.raises(ValueError, match='no AA slug'):
        aa.records([{'id': 'uuid', 'release': {'slug': 'base'}, 'intelligenceIndex': 40,
                     'suffix': 'High', 'intelligenceIndexCostPerTask': 0.3}])


def test_intelligence_uses_complete_catalogue_when_leaderboard_only_has_release(monkeypatch):
    preview = [{'id': 'uuid', 'release': {'slug': 'base'}, 'intelligenceIndex': 40,
                'intelligenceIndexCostPerTask': 0.3}]
    models = [{'slug': f'base-{i}', 'intelligenceIndex': 40, 'intelligenceIndexCostPerTask': {'cost': {'total': 0.3}}}
              for i in range(aa.MIN_PRICED)]
    monkeypatch.setattr(aa, 'fetch_text', lambda url: flight({'initialModels': preview}))
    monkeypatch.setattr(aa_data, 'model_catalogue', lambda: (models, 'https://artificialanalysis.ai/models/base'))
    monkeypatch.setattr(aa, 'api_scores', lambda: ({'base-0': {'score': 40.01}}, None))
    monkeypatch.setattr(aa, 'index_version', lambda: '5.0.1')
    doc, _, _ = aa.source_aa()
    assert len(doc['data']) == aa.MIN_PRICED
    assert doc['data'][0]['slug'] == 'base-0' and doc['data'][0]['intelligence_index'] == 40.01
    assert doc['data'][0]['aa_cost_per_task_intelligence_usd'] == 0.3
    assert doc['versions'] == {'aa_intelligence:intelligence': '5.0.1'}


def test_split_flight_records_keep_evaluations_and_domain_costs():
    page = flight({'initialModels': [{'slug': 'm-high', 'harveyLab': 0.6, 'weightedIndex': 60,
                                      'costPerTask': {'total': 0.25}, 'timePerTaskSeconds': 120}]}, split=True)
    assert aa_evaluations.merge(aa_evaluations._objects(page))['m-high']['harvey_lab'] == 0.6
    assert aa_evaluations._index_models(page)[0]['costPerTask']['total'] == 0.25


@pytest.mark.parametrize('task', ['provider_voice', 'text_to_image', 'text_to_video', 'image_to_video'])
def test_renamed_pricing_header_preserves_media_reference_price(task):
    spec = aa_media.TASK_SPECS[task]
    table = [['', 'Range', 'Model', 'Elo', 'Samples', 'Released', 'Pricing 1'],
             ['1', '1-2', 'Example model', '1200', '2500', 'Nov 2026', '$40.00 /1M chars']]
    selected = aa_media.select_task_table([table], spec)
    doc = aa_media.build_multimodal_snapshot({task: selected})
    row = doc['modules'][spec['module']]['tasks'][task]['rows'][0]
    assert row['quality_score'] == 1200 and row['api_price_usd'] == 40
    assert row['api_price_unit'] == '1M chars'
    assert parse_benchmarks('mm', doc)[0]['score'] == 1200


def test_methodology_patch_version_is_preserved(monkeypatch):
    monkeypatch.setattr(aa, 'fetch_text', lambda url: '<h3>Version 5.0.1</h3><p>November 2026 to current</p>')
    assert aa.index_version() == '5.0.1'


def test_api_reads_every_page_and_keeps_variant_identity(monkeypatch):
    calls = []
    monkeypatch.setattr(aa, 'api_key', lambda: 'test-only-key')
    def response(request, timeout):
        calls.append(request.full_url)
        assert request.get_header('X-api-key') == 'test-only-key'
        page = len(calls)
        return BytesIO(json.dumps({'data': [{'slug': f'm-variant-{page}', 'name': 'M', 'evaluations': {
            'artificial_analysis_intelligence_index': 40+page}}],
            'pagination': {'page': page, 'total_pages': 2, 'has_more': page == 1}}).encode())
    monkeypatch.setattr(aa, 'urlopen', response)
    scores, error = aa.api_scores()
    assert error is None and scores['m-variant-2']['score'] == 42
    assert calls == [aa.AA_API_URL+'?page=1', aa.AA_API_URL+'?page=2']


def test_api_later_page_failure_discards_partial_scores(monkeypatch):
    monkeypatch.setattr(aa, 'api_key', lambda: 'test-only-key')
    def response(request, timeout):
        if request.full_url.endswith('page=2'):
            raise HTTPError(request.full_url, 429, 'rate limited', {}, None)
        return BytesIO(json.dumps({'data': [{'slug': 'first', 'evaluations': {
            'artificial_analysis_intelligence_index': 40}}],
            'pagination': {'page': 1, 'total_pages': 2, 'has_more': True}}).encode())
    monkeypatch.setattr(aa, 'urlopen', response)
    scores, error = aa.api_scores()
    assert scores == {} and error == 'AA API: HTTPError 429'
    assert 'test-only-key' not in error


def test_api_published_cost_completes_missing_page_cost_without_estimating():
    api = {'m-high': {'score': 50, 'cost': 0.2346}, 'api-only': {'score': 55, 'cost': 0.5, 'price_in': 2}}
    rows = {r['slug']: r for r in aa.records([{'slug': 'm-high', 'intelligenceIndex': 50,
                                              'intelligenceIndexCostPerTask': 0.234567}], api)}
    assert rows['m-high']['aa_cost_per_task_intelligence_usd'] == 0.234567
    assert rows['m-high']['cost_source'] == 'page'
    assert rows['api-only']['aa_cost_per_task_intelligence_usd'] == 0.5
    assert rows['api-only']['intelligence_status'] == 'ok'
    assert rows['api-only']['list_price_1m_input'] == 2


def test_update_badges_survive_expiry_of_intelligence_badge(monkeypatch):
    page = flight({'value': {'scicode': {'type': 'underReview', 'description': 'Dataset audit'},
                            'vials-aa': {'type': 'new'}}, 'children': {
        'evaluations': [{'slug': 'harvey-lab-aa', 'change': {'type': 'updated', 'description': 'v1.1'}}]}}, split=True)
    monkeypatch.setattr(aa, 'fetch_text', lambda url: page)
    badges = aa.updates()
    assert badges['scicode']['type'] == 'underReview'
    assert aa_evaluations.versions(badges, '5.0.1')['aa_eval:harvey_lab'] == 'v1.1'
