"""Adversarial checks: fake backends only, no live secrets, Mac or network."""
import asyncio
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for root in ('/opt/walter-secrets', '/opt/walter-computer', '/opt/walter-browse'):
    if root not in sys.path: sys.path.insert(0, root)
import walter_capabilities as capabilities
from walter_platform import harness
from walter_secrets import service as secret_service
from walter_secrets.vault import Vault
from walter_computer.operator import OperatorSessions


class FakeMCP:
    def __init__(self): self.tools, self.metadata = {}, {}
    def tool(self, **metadata):
        def decorate(function):
            self.tools[function.__name__] = function
            self.metadata[function.__name__] = metadata
            return function
        return decorate


class FakeVault(Vault):
    identifier = '00000000-0000-4000-8000-000000000001'
    password = 'fake-secret-never-live'
    def __init__(self):
        super().__init__()
        self.value_calls = []
    def items(self):
        return [{'id': self.identifier, 'type': 1, 'name': 'Fictional service',
                 'login': {'username': 'fictional-user', 'password': self.password,
                           'uris': [{'uri': 'https://fake:fake-url-secret@example.test/?token=fake-query-secret'}]},
                 'fields': [{'name': 'api_key', 'value': 'fake-hidden-field', 'type': 1}]}]
    def value(self, reference, field):
        self.value_calls.append((reference, field))
        raise AssertionError('metadata API must not request a value')


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        # Unit tests exercise boundary policy, not the OS thread executor. The sandbox
        # can stall asyncio executor shutdown; inline dispatch also guarantees no worker survives.
        async def inline(function, *args, **kwargs): return function(*args, **kwargs)
        dispatcher = patch.object(capabilities.asyncio, 'to_thread', new=inline)
        dispatcher.start(); self.addCleanup(dispatcher.stop)
        self.mcp = FakeMCP()
        capabilities.register(self.mcp, client='codex')

    def test_registration_does_not_import_optional_modules(self):
        with patch.object(capabilities, '_module', side_effect=AssertionError('eager import')) as module:
            other = FakeMCP()
            capabilities.register(other, client='dsh')
            self.assertIn('secret_search', other.tools)
            self.assertIn('computer_use', other.tools)
            module.assert_not_called()

    def test_secret_metadata_and_reference_do_not_read_values(self):
        vault = FakeVault()
        service = SimpleNamespace(search=lambda q, k, n: secret_service.search(q, k, n, vault=vault),
                                  reference=lambda item, field: secret_service.reference(item, field, vault=vault))
        with patch.object(capabilities, '_module', return_value=service):
            search = self.mcp.tools['secret_search']('Fictional', 'login', 1)
            reference = self.mcp.tools['secret_reference']('bw:' + vault.identifier, 'api_key')
        self.assertEqual(json.loads(search)['items'][0]['uris'], ['https://example.test'])
        self.assertFalse(json.loads(reference)['value_disclosed'])
        self.assertEqual(vault.value_calls, [])
        for value in (vault.password, 'fake-url-secret', 'fake-query-secret', 'fake-hidden-field'):
            self.assertNotIn(value, search + reference)

    def test_optional_module_failure_is_local_and_error_message_private(self):
        async def browse(args): return json.dumps({'success': True, 'source': 'fake-browse'})
        def modules(which, name):
            if which == 'secrets': raise ModuleNotFoundError('fake-token-that-must-not-cross-boundary')
            return SimpleNamespace(browse=browse)
        with patch.object(capabilities, '_module', side_effect=modules):
            failure = self.mcp.tools['secret_search']('Fictional')
            success = asyncio.run(self.mcp.tools['walter_browse'](query='fictional'))
        self.assertEqual(json.loads(failure)['module'], 'secrets')
        self.assertNotIn('fake-token', failure)
        self.assertTrue(json.loads(success)['success'])

    def test_no_generic_execute_or_raw_secret_tool_and_router_tools_are_honest(self):
        """2026-10-22 (owner): the router's tools are the same in every runtime (walter_route / walter_run /
        walter_generate / walter_plans); the harness keeps its own model, generation is flagged as costly."""
        self.assertEqual(set(self.mcp.tools), {'walter_modules', 'secret_search', 'secret_reference', 'walter_browse',
                                             'walter_route', 'walter_run', 'walter_generate', 'walter_plans',
                                             'computer_use'})
        self.assertNotIn('grants', inspect.signature(self.mcp.tools['computer_use']).parameters)
        self.assertNotIn('permissions', inspect.signature(self.mcp.tools['computer_use']).parameters)
        self.assertNotIn('command', inspect.signature(self.mcp.tools['secret_reference']).parameters)
        self.assertTrue(self.mcp.metadata['walter_route']['annotations'].readOnlyHint)
        self.assertTrue(self.mcp.metadata['walter_generate']['annotations'].destructiveHint)
        self.assertFalse(self.mcp.metadata['computer_use']['annotations'].readOnlyHint)

    def test_computer_permissions_come_only_from_external_policy(self):
        made = []
        def factory():
            made.append(True)
            raise AssertionError('backend must not start before permission checks')
        pool = OperatorSessions(factory)
        with patch.object(capabilities, '_computer_pool', return_value=pool), \
             patch.object(capabilities, '_policy', return_value=frozenset({'read'})):
            result = asyncio.run(self.mcp.tools['computer_use']('fake-session', 'click',
                                 {'x': 1, 'y': 1, 'grants': ['read', 'input'], 'permissions': ['input']}))
        parsed = json.loads(result)
        self.assertEqual(parsed['code'], 'authorization_required')
        self.assertIn('input', parsed['required_scopes'])
        self.assertEqual(made, [])

    def test_pixels_require_server_policy_even_for_capture(self):
        pool = OperatorSessions(lambda: (_ for _ in ()).throw(AssertionError('no capture allowed')))
        with patch.object(capabilities, '_computer_pool', return_value=pool), \
             patch.object(capabilities, '_policy', return_value=frozenset({'read'})):
            result = asyncio.run(self.mcp.tools['computer_use']('fake-session', 'capture', {'app': 'Fictional'}))
        self.assertIn('pixels', json.loads(result)['required_scopes'])

    def test_unknown_client_has_no_policy_and_world_writable_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp)/'computer-policy.json'
            policy.write_text(json.dumps({'version': 1, 'clients': {'codex': ['read']}}))
            policy.chmod(0o600)
            with patch.object(capabilities, 'Path', return_value=policy):
                self.assertEqual(capabilities._policy('unknown'), frozenset())
                self.assertEqual(capabilities._policy('codex'), frozenset({'read'}))
                policy.chmod(0o666)
                with self.assertRaises(PermissionError): capabilities._policy('codex')

    def test_different_harnesses_use_different_computer_namespaces(self):
        other = FakeMCP(); capabilities.register(other, client='dsh')
        calls = []
        class Pool:
            def call(self, namespace, action, arguments, *, grants):
                calls.append(namespace)
                return {'ok': True}
        with patch.object(capabilities, '_computer_pool', return_value=Pool()), \
             patch.object(capabilities, '_policy', return_value=frozenset({'read'})):
            asyncio.run(self.mcp.tools['computer_use']('same-id', 'close'))
            asyncio.run(other.tools['computer_use']('same-id', 'close'))
        self.assertNotEqual(calls[0], calls[1])

    def test_router_tools_pass_no_shell_word_and_use_the_router_command(self):
        with patch.object(capabilities.subprocess, 'run') as run:
            denied = self.mcp.tools['walter_route'](task='coding;do-something')
            self.assertFalse(json.loads(denied)['ok'])
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 0, stdout='{"model_id":"fictional-model"}', stderr='')
            accepted = self.mcp.tools['walter_route'](request='une landing page', task='frontend')
            self.assertEqual(json.loads(accepted)['model_id'], 'fictional-model')
            args, kwargs = run.call_args
            self.assertEqual(args[0], ['walter-router', 'route', 'une landing page', '--task', 'frontend', '--agent'])
            self.assertFalse(kwargs.get('shell', False))
            self.mcp.tools['walter_route'](request='analyse cette vidéo', task='vision', require='video_input')
            self.assertEqual(run.call_args[0][0], ['walter-router', 'pick', 'vision', '--require', 'video_input', '--agent'])
            self.assertFalse(json.loads(self.mcp.tools['walter_generate']('x', role='a b'))['ok'])

    def test_walter_run_refuses_media_and_reports_the_route_it_ran(self):
        decision = {'task': 'general', 'level': 'L2', 'execution': [{'provider': 'fictional'}]}
        with patch.object(capabilities, '_router_decision', return_value=decision), \
             patch.object(capabilities, '_walter_llm', return_value=('réponse', 'fictional/model')) as llm:
            out = json.loads(self.mcp.tools['walter_run']('compare A et B', request='compare A et B'))
        self.assertEqual((out['output'], out['route']), ('réponse', 'fictional/model'))
        self.assertEqual(llm.call_args[0][0], 'general/L2')
        with patch.object(capabilities, '_router_decision', return_value={'task': 'text_to_video'}):
            self.assertFalse(json.loads(self.mcp.tools['walter_run']('une vidéo'))['ok'])

    def test_browse_rejects_filesystem_session_identifiers_before_backend(self):
        from walter_browse import facade
        for invalid in ('../other', '/tmp/private-session', 'a/../../b', 'a\\b', '.', '..'):
            with self.subTest(session=invalid), patch.object(capabilities, '_module', return_value=facade), \
                 patch.object(facade, '_run_router', side_effect=AssertionError('backend IO forbidden')) as backend:
                result = asyncio.run(self.mcp.tools['walter_browse'](query='fictional', session_id=invalid))
                self.assertFalse(json.loads(result).get('success', json.loads(result).get('ok', True)))
                backend.assert_not_called()

    def test_http_operator_is_disabled_before_policy_or_backend(self):
        remote = FakeMCP()
        capabilities.register(remote, client='codex', local_control=False)
        with patch.object(capabilities, '_computer_pool') as pool, patch.object(capabilities, '_policy') as policy:
            result = asyncio.run(remote.tools['computer_use']('fake-session', 'click', {'x': 1, 'y': 2}))
        self.assertEqual(json.loads(result)['code'], 'computer_requires_local_stdio_client')
        pool.assert_not_called(); policy.assert_not_called()

    def test_real_fastmcp_schema_has_no_execution_or_grant_endpoint(self):
        from mcp.server.fastmcp import FastMCP
        server = FastMCP('walter-capabilities-unit-test')
        with patch.object(capabilities, '_module', side_effect=AssertionError('eager module access')):
            capabilities.register(server, client='unit-test')
            schemas = asyncio.run(server.list_tools())
        by_name = {tool.name: tool for tool in schemas}
        self.assertEqual(set(by_name), set(self.mcp.tools))
        self.assertEqual(set(by_name['computer_use'].inputSchema['properties']), {'session_id', 'action', 'arguments'})
        self.assertFalse(by_name['computer_use'].annotations.readOnlyHint)
        self.assertTrue(by_name['secret_search'].annotations.readOnlyHint)


class InstallerRaceRegression(unittest.TestCase):
    def test_concurrent_change_during_prepare_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)/'codex'; home.mkdir()
            config = home/'config.toml'
            original = 'model = "native"\n'
            concurrent = original + 'approval_policy = "on-request"\n'
            config.write_text(original)
            prepare = harness.prepare
            def concurrent_prepare(*args, **kwargs):
                result = prepare(*args, **kwargs)
                config.write_text(concurrent)
                return result
            with patch.object(harness, 'prepare', side_effect=concurrent_prepare):
                with self.assertRaises(RuntimeError):
                    harness.attach('codex', home, apply=True, backup_root=Path(tmp)/'backups')
            self.assertEqual(config.read_text(), concurrent)


if __name__ == '__main__': unittest.main()
