"""Public Arena HTML observed 2026-10-29; mock its public CLI transport, no account/model/DB."""
import base64
import gzip
import json
import re
import subprocess
from urllib.error import HTTPError

import pytest
from walter_router.research.benchmarks import arena

PUBLIC_DATA = '{"id":"leaderboard-sets/public/leaderboards/text-overall-style_control/leaderboard-snapshots/latest","entries":[{"rank":1,"modelDisplayName":"Gemini 4 Carbon (High)","rating":1527.5065447464403,"ratingLower":1518.0976265288389,"ratingUpper":1536.9154629640418,"votes":4403},{"rank":2,"modelDisplayName":"Gemini 4 Argon (High)","rating":1520.254646597456,"ratingLower":1513.9807620604795,"ratingUpper":1526.5285311344326,"votes":11889}]}'
PUBLIC_PAGE = '<script>self.__next_f.push([1,' + json.dumps(PUBLIC_DATA) + '])</script>'


def browser(monkeypatch, *, fail=None, metadata=None, payload=None):
    encoded = base64.b64encode(gzip.compress(PUBLIC_PAGE.encode() if payload is None else payload)).decode()
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        action = argv[3]
        if fail == action:
            return subprocess.CompletedProcess(argv, 1, '', 'do-not-echo-fixture')
        if action == 'eval':
            expr = argv[4]
            if 'CompressionStream' in expr:
                result = {'url':'https://arena.ai/leaderboard/chat/text', 'htmlBytes':len(PUBLIC_PAGE.encode()),
                          'encodedLength':len(encoded), **(metadata or {})}
            else:
                start, end = map(int, re.search(r'slice\((\d+),(\d+)\)', expr).groups())
                result = encoded[start:end]
            return subprocess.CompletedProcess(argv, 0, json.dumps({'ok':True,'result':result}), '')
        return subprocess.CompletedProcess(argv, 0, 'public-tab', '')
    monkeypatch.setattr(subprocess, 'run', run)
    return calls


def test_existing_parser_reads_observed_public_format():
    result = arena.arena_board(PUBLIC_PAGE)
    assert result['kind'] == 'elo' and len(result['rows']) == 2


def test_transport_falls_back_on_http_failure_without_changing_board_keys(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'chat/text':'text'})
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: (_ for _ in ()).throw(HTTPError(url,500,'server',None,None)))
    calls = browser(monkeypatch)
    doc, _, _ = arena.source_arena()
    assert len(doc['boards']['text']['rows']) == 2
    assert calls[-1][3] == 'close'
    assert all('login' not in call for call in calls)
    assert len({call[2] for call in calls}) == 1


def test_public_cli_html_roundtrip_is_bounded_and_always_closes(monkeypatch):
    calls = browser(monkeypatch)
    assert arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3) == PUBLIC_PAGE
    assert calls[-1][3] == 'close'


def test_cli_failure_is_typed_and_does_not_echo_stderr(monkeypatch):
    calls = browser(monkeypatch, fail='nav')
    with pytest.raises(RuntimeError, match='browser') as error:
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)
    assert 'do-not-echo-fixture' not in str(error.value)
    assert calls[-1][3] == 'close'


@pytest.mark.parametrize('metadata', [{'htmlBytes':100000000}, {'encodedLength':1000000000},
                                     {'url':'https://outside.invalid/private'}, {'htmlBytes':True}])
def test_untrusted_browser_result_is_rejected_and_closed(monkeypatch, metadata):
    calls = browser(monkeypatch, metadata=metadata)
    with pytest.raises(RuntimeError):
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)
    assert calls[-1][3] == 'close'


def test_source_browser_budget_is_shared_between_boards(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'a':'a','b':'b','c':'c'})
    monkeypatch.setattr(arena, '_board_matches', lambda key,board: bool(board and board.get('rows')))
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(arena, 'BROWSER_BUDGET', 2)
    clock=[0.0]
    monkeypatch.setattr(arena.time, 'monotonic', lambda: clock[0])
    calls=[]
    def exhaust(url, *, timeout, **kwargs):
        calls.append(timeout)
        clock[0] += 2
        return PUBLIC_PAGE
    monkeypatch.setattr(arena, '_browser_text', exhaust)
    doc, _, _ = arena.source_arena()
    assert len(calls) == 1 and len(doc['boards']) == 1 and set(doc['errors']) == {'b','c'}


def test_http_success_does_not_start_a_browser(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'chat/text':'text'})
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: PUBLIC_PAGE)
    monkeypatch.setattr(arena, '_browser_text', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('unexpected browser')))
    doc, _, _ = arena.source_arena()
    assert doc['errors'] == {} and len(doc['boards']['text']['rows']) == 2


def test_timeout_still_closes_only_its_dedicated_session(monkeypatch):
    calls=[]
    def timed_out(argv, **kwargs):
        calls.append(argv)
        assert 0 < kwargs['timeout'] <= 3
        if argv[3] == 'nav':
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', timed_out)
    with pytest.raises(RuntimeError, match='browser'):
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)
    assert calls[-1][3] == 'close' and len({call[2] for call in calls}) == 1


def test_compressed_expansion_cannot_exceed_host_byte_bound(monkeypatch):
    monkeypatch.setattr(arena, 'MAX_BYTES', 4096)
    calls=browser(monkeypatch, payload=b'x' * 1000000, metadata={'htmlBytes':4096})
    with pytest.raises(RuntimeError, match='compressed HTML'):
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)
    assert calls[-1][3] == 'close'


def test_failure_to_close_is_not_a_successful_browser_read(monkeypatch):
    browser(monkeypatch, fail='close')
    with pytest.raises(RuntimeError, match='browser'):
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)


def test_close_failure_does_not_hide_the_primary_error(monkeypatch):
    def fail(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0 if argv[3]=='new' else 1, '', 'do-not-echo-fixture')
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='browser command failed') as error:
        arena._browser_text('https://arena.ai/leaderboard/chat/text', timeout=3)
    assert any('cleanup also failed' in note for note in error.value.__notes__)
    assert 'do-not-echo-fixture' not in str(error.value)


def test_failed_http_transport_is_not_repeated_for_every_board(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'a':'a','b':'b','c':'c'})
    monkeypatch.setattr(arena, '_board_matches', lambda key,board: bool(board and board.get('rows')))
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    reads=[]
    def unavailable(url):
        reads.append(url)
        raise OSError()
    monkeypatch.setattr(arena, 'fetch_text', unavailable)
    monkeypatch.setattr(arena, '_browser_text', lambda *a, **kw: PUBLIC_PAGE)
    doc, _, _ = arena.source_arena()
    assert len(doc['boards']) == 3 and len(reads) == 1


def test_collection_reuses_one_anonymous_session_and_closes_once(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'a':'a','b':'b','c':'c'})
    monkeypatch.setattr(arena, '_board_matches', lambda key,board: bool(board and board.get('rows')))
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: (_ for _ in ()).throw(OSError()))
    calls=browser(monkeypatch)
    doc, _, _ = arena.source_arena()
    assert len(doc['boards']) == 3
    assert len({call[2] for call in calls}) == 1
    assert sum(call[3]=='new' for call in calls) == 1
    assert sum(call[3]=='nav' for call in calls) == 3
    assert sum(call[3]=='close' for call in calls) == 1


def test_generic_text_redirect_cannot_be_stored_as_french(monkeypatch):
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'text/french':'text_french'})
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: PUBLIC_PAGE)
    browser(monkeypatch)
    with pytest.raises(ValueError, match='only 0 boards'):
        arena.source_arena()


def test_matching_french_board_keeps_its_own_identity(monkeypatch):
    french=PUBLIC_PAGE.replace('text-overall-style_control','text-french-style_control')
    monkeypatch.setattr(arena, 'ARENA_BOARDS', {'text/french':'text_french'})
    monkeypatch.setattr(arena.time, 'sleep', lambda *a: None)
    monkeypatch.setattr(arena, 'fetch_text', lambda url: french)
    doc, _, _ = arena.source_arena()
    assert set(doc['boards']) == {'text_french'}
    assert 'text-french-style_control/' in doc['boards']['text_french']['leaderboard_id']
