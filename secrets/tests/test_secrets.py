from __future__ import annotations
import base64
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import pytest

from walter_secrets import service, unlock
from walter_secrets.masking import Masker, public_error
from walter_secrets.vault import Vault, SecretError

ITEM = '00000000-0000-4000-8000-000000000001'
FAKE = 'fake-test-password!not-live'


class FakeVault(Vault):
    def __init__(self):
        super().__init__()
        self.reads = []
        self.data = [{'id': ITEM, 'name': 'Test login', 'type': 1,
                      'login': {'username': 'test-user', 'password': FAKE,
                                'uris': [{'uri': 'https://user:fake-uri-secret@example.test/login?token=fake-query-secret#fake-fragment'}]},
                      'fields': [{'name': 'api key', 'type': 1, 'value': 'fake-api-key-not-live'}]}]

    def items(self):
        return self.data

    def value(self, ref, field):
        self.reads.append((ref, field))
        return super().value(ref, field)


@pytest.fixture
def vault():
    return FakeVault()


def test_imports_without_any_harness():
    root = str(Path(__file__).resolve().parents[1])
    program = '''import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'agent', 'tools', 'hermes_cli', 'hermes'}:
            raise AssertionError('host import: ' + fullname)
sys.meta_path.insert(0, Block())
sys.path.insert(0, ROOT)
from walter_secrets import service, vault, masking, otp, secrets_sync, vault_react, unlock
assert not any(x in sys.modules for x in ('agent', 'tools', 'hermes_cli'))
'''.replace('ROOT', repr(root))
    completed = subprocess.run([sys.executable, '-I', '-c', program], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_metadata_does_not_disclose_values_or_signed_urls(vault):
    result = service.search('Test', vault=vault)
    encoded = json.dumps(result)
    for value in (FAKE, 'fake-uri-secret', 'fake-query-secret', 'fake-fragment', 'fake-api-key-not-live'):
        assert value not in encoded
    assert result['items'][0]['uris'] == ['https://example.test']
    assert result['items'][0]['handle'] == 'bw:' + ITEM
    assert vault.reads == []


def test_reference_is_value_free_and_round_trips_custom_field(vault):
    result = service.reference('bw:' + ITEM, 'api key', vault=vault)
    assert service.parse_reference(result['reference']) == (ITEM, 'field:api key')
    assert result['value_disclosed'] is False
    assert vault.reads == []


@pytest.mark.parametrize('ref', ['https://evil.test', 'walter-secret://bitwarden/not-a-uuid/password',
                                'walter-secret://bitwarden/' + ITEM + '/password?token=x',
                                'walter-secret://bitwarden/' + ITEM + '/%00'])
def test_reference_validation(ref):
    with pytest.raises(ValueError):
        service.parse_reference(ref)


def test_unknown_field_rejected_before_value_read(vault):
    with pytest.raises(ValueError):
        service.reference(ITEM, 'missing', vault=vault)
    assert vault.reads == []


def test_execution_injects_env_discards_even_transformed_output(vault, capfd):
    ref = service.reference(ITEM, 'password', vault=vault)['reference']
    script = 'import os,sys,base64; v=os.environ["DEMO_KEY"]; print(v); print(base64.b64encode(v.encode())); print(v,file=sys.stderr); sys.exit(0 if v.startswith("fake-test") else 9)'
    result = service.execute([sys.executable, '-c', script], {'DEMO_KEY': ref}, vault=vault, audit_fn=lambda *a, **k: None)
    captured = capfd.readouterr()
    assert captured.out == captured.err == ''
    assert result == {'success': True, 'returncode': 0, 'timed_out': False, 'output': 'discarded', 'bindings_used': 1}
    assert FAKE not in json.dumps(result)
    assert 'DEMO_KEY' not in os.environ


def test_execution_timeout_stops_process(vault):
    ref = service.reference(ITEM, 'password', vault=vault)['reference']
    result = service.execute([sys.executable, '-c', 'import time; time.sleep(30)'], {'DEMO_KEY': ref},
                             timeout=.1, vault=vault, audit_fn=lambda *a, **k: None)
    assert result['timed_out'] and result['returncode'] < 0


def test_execution_oserror_does_not_echo_command(vault):
    ref = service.reference(ITEM, 'password', vault=vault)['reference']
    with pytest.raises(SecretError) as caught:
        service.execute(['/nonexistent/' + FAKE], {'DEMO_KEY': ref}, vault=vault, audit_fn=lambda *a, **k: None)
    assert FAKE not in str(caught.value)


def test_masker_handles_short_values_encodings_and_overlap():
    masker = Masker()
    masker.register(FAKE)
    masker.register('123456', '[otp]')
    masker.register('long-overlap', '[long]')
    masker.register('overlap', '[short]')
    result = masker.walk({'output': [FAKE, base64.b64encode(FAKE.encode()).decode(), 'code 123456', 'long-overlap']})
    assert result == {'output': ['[secret]', '[secret]', 'code [otp]', '[long]']}


def test_masker_keeps_known_values_when_vault_is_unavailable():
    source = lambda: {FAKE: '[known]'}
    masker = Masker(source, ttl=0)
    assert masker.scrub(FAKE) == '[known]'
    masker.source = lambda: (_ for _ in ()).throw(RuntimeError(FAKE))
    assert masker.scrub(FAKE) == '[known]'
    assert FAKE not in json.dumps(public_error(RuntimeError(FAKE)))


def test_hermes_hooks_share_the_core_without_resolving_in_terminal_arguments(vault, monkeypatch):
    from walter_secrets.ports import hermes
    monkeypatch.setattr(hermes, 'VAULT', vault)
    monkeypatch.setattr(hermes, 'MASKER', Masker(lambda: vault.maskable()))
    monkeypatch.setattr(hermes, 'audit', lambda *a, **kw: None)
    placeholder = '{{bw:' + ITEM + ':password}}'
    result = hermes._pre_tool_call('terminal', {'command': 'curl -H "Authorization: ' + placeholder + '" https://example.test'}, 'test')
    assert result['action'] == 'modify'
    assert 'walter-secret get' in result['args']['command']
    assert FAKE not in json.dumps(result)
    assert FAKE not in hermes._transform_tool_result('terminal', 'echo ' + FAKE)


def test_hermes_tool_registration_preserved(monkeypatch):
    from walter_secrets.ports import hermes
    monkeypatch.setattr(hermes, 'cleanup_files', lambda: None)
    class Context:
        def __init__(self): self.tools, self.hooks = {}, {}
        def register_tool(self, **kw): self.tools[kw['name']] = kw
        def register_hook(self, name, fn): self.hooks[name] = fn
    context = Context()
    hermes.register(context)
    assert set(context.tools) == {'secret_search', 'secret_file', 'secret_reveal', 'secret_create_login',
                                  'secret_capture_totp', 'secret_fill', 'secret_otp'}
    assert set(context.hooks) == {'pre_tool_call', 'transform_tool_result', 'transform_terminal_output'}


def test_unlock_uses_password_environment_not_argv(tmp_path, monkeypatch):
    cache = tmp_path/'session'
    monkeypatch.setattr(unlock.settings, 'SESSION', cache)
    calls = []
    def run(argv, *, env=None):
        calls.append((argv, env))
        if argv[0] == 'age':
            return json.dumps({'services': {'bitwarden': {'master_password': FAKE}}})
        if argv[:2] == ['bw', 'status']:
            return json.dumps({'status':'locked'})
        return 'fake-session-token-not-live'
    monkeypatch.setattr(unlock, '_run', run)
    assert unlock.session() == 'fake-session-token-not-live'
    assert FAKE not in repr([c[0] for c in calls])
    assert next(env for argv,env in calls if argv[:2] == ['bw','unlock'])['WALTER_BW_MASTER'] == FAKE
    assert cache.stat().st_mode & 0o777 == 0o600


def test_sync_restart_is_deployment_binding(monkeypatch):
    from walter_secrets import secrets_sync
    monkeypatch.setattr(secrets_sync.settings, 'ENV_CONSUMERS',
                        [{'unit': 'sample.service', 'user': True, 'restart': ['host-adapter', 'graceful-restart']}])
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(secrets_sync.subprocess, 'run', run)
    monkeypatch.setattr(secrets_sync.time, 'sleep', lambda _: None)
    assert secrets_sync.restart([('sample.service', True)]) == []
    assert calls[0] == ['host-adapter', 'graceful-restart']


def test_cli_local_reference_does_not_read_value(vault, monkeypatch, capsys):
    from walter_secrets.cli import safe_main
    monkeypatch.setattr(service, 'VAULT', vault)
    assert safe_main(['ref', ITEM, 'password']) == 0
    assert capsys.readouterr().out.strip() == 'walter-secret://bitwarden/' + ITEM + '/password'
    assert vault.reads == []


def test_unlock_preserves_noninteractive_relogin_without_password_argv(tmp_path, monkeypatch):
    monkeypatch.setattr(unlock.settings, 'SESSION', tmp_path/'session')
    calls = []
    def run(argv, *, env=None):
        calls.append((argv, env))
        if argv[0] == 'age':
            return json.dumps({'services': {'bitwarden': {'master_password': FAKE}}})
        if argv[:2] == ['bw','status']:
            return json.dumps({'status':'unauthenticated'})
        if argv[:2] == ['bw','unlock']:
            return 'fake-session-token-not-live'
        return ''
    monkeypatch.setattr(unlock, '_run', run)
    assert unlock.session() == 'fake-session-token-not-live'
    login = next((argv,env) for argv,env in calls if argv[:2] == ['bw','login'])
    assert '--passwordenv' in login[0]
    assert login[1]['WALTER_BW_MASTER'] == FAKE
    assert FAKE not in repr([argv for argv,env in calls])
