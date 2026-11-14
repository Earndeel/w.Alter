"""Deploy freshness (SOCLE A8): static import closure, declared roots, staleness, gated restart. No systemd: unit
facts are injected, files live in temp dirs with fake mtimes."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_platform import contracts, deploy  # noqa: E402

T0 = 1_800_000_000.0          # unit start time used by every test


def write(path, text='', mtime=T0 - 3600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (mtime, mtime))
    return path


def facts(argv, workdir='/', started=T0, active=True, env=None):
    return {'loaded': True, 'active': active, 'started_at': started, 'argv': argv, 'workdir': workdir, 'env': env or {}}


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'walter'
        r = self.root
        # two first-party libraries; the service imports only mem_lib (through a relative import inside it)
        write(r / 'mem' / 'mem_lib' / '__init__.py')
        write(r / 'mem' / 'mem_lib' / 'gateway.py', 'from . import llm\nfrom .db import connect\napp = object()\n')
        write(r / 'mem' / 'mem_lib' / 'llm.py', 'import json\n')
        write(r / 'mem' / 'mem_lib' / 'db.py', 'import os\n')
        write(r / 'mem' / 'mem_lib' / 'unused.py', '')
        write(r / 'mem' / 'tests' / 'test_x.py', '')
        write(r / 'other' / 'other_lib' / '__init__.py', '')
        write(r / 'other' / 'other_lib' / 'big.py', '')
        self.search = [str(r / 'mem'), str(r / 'other')]
        self.kw = {'walter_root': str(r), 'interp_path': lambda interp, wd: self.search}

    def tearDown(self):
        self.tmp.cleanup()

    def assess(self, f, declared=None):
        return deploy.assess('svc', f, declared, **self.kw)


class PythonGraphTests(Tree):
    def test_uvicorn_service_follows_only_what_it_imports(self):
        f = facts(['/usr/local/bin/walter-python', '-m', 'uvicorn', 'mem_lib.gateway:app', '--port', '1'])
        row = self.assess(f)
        self.assertEqual(row['kind'], 'python')
        self.assertFalse(row['stale'])
        files = deploy.code_for(f, **self.kw)['files']
        names = {Path(x).name for x in files}
        self.assertEqual(names, {'__init__.py', 'gateway.py', 'llm.py', 'db.py'})
        # a library the service never imports changes: still fresh
        write(self.root / 'other' / 'other_lib' / 'big.py', '', T0 + 600)
        write(self.root / 'mem' / 'mem_lib' / 'unused.py', '', T0 + 600)
        write(self.root / 'mem' / 'tests' / 'test_x.py', '', T0 + 600)
        self.assertFalse(self.assess(f)['stale'])
        # the library it imports changes after the start: stale (the 2026-11-11 incident)
        write(self.root / 'mem' / 'mem_lib' / 'llm.py', 'import json\n', T0 + 600)
        row = self.assess(f)
        self.assertTrue(row['stale'])
        self.assertTrue(row['newest'].endswith('mem_lib/llm.py'))
        self.assertEqual(row['behind_s'], 600)

    def test_script_with_sys_path_insert_and_transitive_import(self):
        write(self.root / 'iface' / 'bot.py',
              'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parent))\n'
              'import fmt\n')
        write(self.root / 'iface' / 'fmt.py', 'def f():\n    from other_lib import big\n')
        f = facts(['/usr/local/bin/walter-python', str(self.root / 'iface' / 'bot.py')], workdir='/root')
        names = {Path(x).name for x in deploy.code_for(f, **self.kw)['files']}
        self.assertEqual(names, {'bot.py', 'fmt.py', '__init__.py', 'big.py'})
        write(self.root / 'mem' / 'mem_lib' / 'llm.py', '', T0 + 600)   # not imported by the bot
        self.assertFalse(self.assess(f)['stale'])

    def test_shell_wrapper_and_package_path_redirect(self):
        # walter_router style: the import name's __path__ points at the module root
        write(self.root / 'router' / 'rpkg' / '__init__.py',
              'from pathlib import Path\n__path__ = [str(Path(__file__).resolve().parent.parent)]\n')
        write(self.root / 'router' / 'plan' / 'quota.py', 'from rpkg.serve import oneshot\n')
        write(self.root / 'router' / 'serve' / 'oneshot.py', '')
        self.search.append(str(self.root / 'router'))
        wrapper = write(self.root / 'router' / 'bin' / 'run',
                        '#!/bin/sh\ncd "$root" && PYTHONPATH="$root" exec walter-python -m rpkg.plan.quota "$@"\n')
        f = facts([str(wrapper)])
        row = self.assess(f)
        self.assertEqual(row['entry'], 'rpkg.plan.quota')
        names = {Path(x).name for x in deploy.code_for(f, **self.kw)['files']}
        self.assertEqual(names, {'run', '__init__.py', 'quota.py', 'oneshot.py'})
        write(self.root / 'router' / 'serve' / 'oneshot.py', '', T0 + 60)
        self.assertTrue(self.assess(f)['stale'])

    def test_binary_and_stopped_units_are_not_judged(self):
        binary = write(Path(self.tmp.name) / 'rclone', '\x7fELF....')
        self.assertIsNone(self.assess(facts([str(binary), 'serve']))['stale'])
        f = facts(['/usr/local/bin/walter-python', '-m', 'mem_lib.gateway'], active=False)
        self.assertIsNone(self.assess(f)['stale'])


class DeclaredRootsTests(Tree):
    def test_node_service_uses_declared_roots_and_files(self):
        write(self.root / 'engine' / 'plugins' / 'a.mjs', '', T0 - 10)
        write(self.root / 'engine' / 'plugins' / 'node_modules' / 'x.js', '', T0 + 999)   # excluded
        write(self.root / 'engine' / 'plugins' / 'README.md', '', T0 + 999)               # not code
        comp = write(Path(self.tmp.name) / 'home' / 'cordis.patch.yml', '', T0 - 5)
        kernel = write(Path(self.tmp.name) / 'opt' / 'dsh.js', '#!/usr/bin/env node\n', T0 + 999)  # frozen, outside
        declared = {'code_roots': [str(self.root / 'engine' / 'plugins')], 'code_files': [str(comp)]}
        row = self.assess(facts([str(kernel), '--profile', 'web']), declared)
        self.assertEqual((row['kind'], row['files'], row['stale']), ('node', 2, False))
        write(comp, 'changed', T0 + 30)
        self.assertTrue(self.assess(facts([str(kernel)]), declared)['stale'])

    def test_status_reads_registry_services_and_skips_timers(self):
        write(self.root / 'mem' / 'mem_lib' / 'db.py', '', T0 + 100)
        registry = {'modules': [
            {'id': 'memory', 'services': ['walter-memory-gateway', 'walter-memory-x.timer']},
            {'id': 'core', 'services': ['dsh-web.service'],
             'service_code': {'dsh-web': {'code_roots': [str(self.root / 'other')]}}}]}
        units = {'walter-memory-gateway': facts(['/usr/local/bin/walter-python', '-m', 'mem_lib.gateway']),
                 'dsh-web': facts(['/usr/bin/node'])}
        out = deploy.status(registry, facts=lambda u: units[u], **self.kw)
        self.assertEqual([r['unit'] for r in out['services']], ['dsh-web', 'walter-memory-gateway'])
        self.assertEqual(out['stale'], ['walter-memory-gateway'])
        self.assertFalse(out['ok'])
        self.assertIn('walter-memory-gateway', deploy.table(out))


class RepairTests(Tree):
    def test_decide_gates(self):
        stale = {'unit': 'walter-llm', 'stale': True}
        self.assertEqual(deploy.decide({'unit': 'x', 'stale': False}), 'none:fresh')
        self.assertEqual(deploy.decide(stale, now=T0), 'restart')
        self.assertEqual(deploy.decide(stale, last_restart=T0 - 600, now=T0), 'defer:rate_limited')
        self.assertEqual(deploy.decide(stale, last_restart=T0 - 4000, now=T0), 'restart')
        engine = {'unit': 'dsh-web', 'stale': True}
        self.assertEqual(deploy.decide(engine, busy=1, now=T0), 'defer:turn_in_flight')
        self.assertEqual(deploy.decide(engine, busy=None, now=T0), 'defer:engine_state_unknown')
        self.assertEqual(deploy.decide(engine, busy=0, now=T0), 'restart')
        self.assertEqual(deploy.decide({'unit': 'walter-telegram', 'stale': True}, busy=2, now=T0), 'defer:turn_in_flight')
        self.assertEqual(deploy.decide(stale, now=T0, enabled=False), 'defer:repair_disabled')
        self.assertEqual(deploy.plan({'services': [stale]}, history={}, now=T0, enabled=False),
                         {'walter-llm': 'defer:repair_disabled'})

    def test_turns_in_flight_reads_open_engine_runs(self):
        class R:
            returncode = 0
            stdout = json.dumps([{'status': 'open', 'runtime': 'dsh', 'seconds': 40},
                                 {'status': 'open', 'runtime': 'dsh', 'seconds': 99999},       # abandoned, not a turn
                                 {'status': 'open', 'runtime': 'claude_code', 'seconds': 10},
                                 {'status': 'ended', 'runtime': 'dsh', 'seconds': 10}])
        self.assertEqual(deploy.turns_in_flight(lambda *a, **k: R()), 1)
        self.assertIsNone(deploy.turns_in_flight(lambda *a, **k: (_ for _ in ()).throw(OSError())))

    def test_restart_dry_run_and_refusal_never_touch_systemd(self):
        os.environ['WALTER_INSTANCE'] = self.tmp.name
        try:
            write(self.root / 'engine' / 'a.mjs', '', T0 + 50)
            registry = {'modules': [{'id': 'core', 'services': ['svc-node'],
                                     'service_code': {'svc-node': {'code_roots': [str(self.root / 'engine')]}}}]}
            calls = []
            runner = lambda cmd, **k: calls.append(cmd)   # noqa: E731
            f = lambda u: facts(['/usr/bin/node'])        # noqa: E731
            out = deploy.restart('svc-node', dry_run=True, facts=f, runner=runner, registry=registry, enabled=True)
            self.assertEqual((out['rc'], out['action'], out['dry_run']), (0, 'restart', True))
            out = deploy.restart('unknown-unit', facts=f, runner=runner, registry=registry)
            self.assertEqual((out['rc'], out['action']), (2, 'refused'))
            self.assertEqual(calls, [])
            # switch off (default in the working tree): deferred, systemd untouched
            out = deploy.restart('svc-node', facts=f, runner=runner, registry=registry, enabled=False)
            self.assertEqual((out['rc'], out['action']), (0, 'defer:repair_disabled'))
            out = deploy.restart('svc-node', facts=f, runner=runner, registry=registry, enabled=False, require_stale=True)
            self.assertEqual(out['rc'], 3)   # the context guardian escalates instead of waiting
            self.assertEqual(calls, [])
            # a real (fake) restart is recorded and rate-limited for the next hour
            class Ok:
                returncode = 0
            starts = {'t': T0}
            f2 = lambda u: facts(['/usr/bin/node'], started=starts['t'])   # noqa: E731

            def runner2(cmd, **k):
                calls.append(cmd)
                starts['t'] = T0 + 100
                return Ok()
            out = deploy.restart('svc-node', facts=f2, runner=runner2, registry=registry, settle=0, enabled=True)
            self.assertEqual((out['rc'], out['action'], out['after']['stale']), (0, 'restart', False))
            self.assertEqual(calls, [['systemctl', 'restart', 'svc-node.service']])
            history = json.loads((Path(self.tmp.name) / 'state' / 'guardians' / 'deploy-restarts.json').read_text())
            self.assertIn('svc-node', history)
            starts['t'] = T0
            out = deploy.restart('svc-node', facts=f2, runner=runner2, registry=registry, settle=0, enabled=True)
            self.assertEqual(out['action'], 'defer:rate_limited')
            self.assertEqual(len(calls), 1)
        finally:
            os.environ.pop('WALTER_INSTANCE', None)


class ContractTests(unittest.TestCase):
    def test_service_code_is_validated(self):
        check = contracts.absolute_path
        contracts._service_code({'dsh-web': {'code_roots': ['/walter/core/engine/plugins']}}, check)
        for bad in ({'x.timer': {'code_roots': ['/a']}}, {'x': {}}, {'x': {'roots': ['/a']}},
                    {'x': {'code_roots': ['relative']}}, []):
            with self.assertRaises(ValueError):
                contracts._service_code(bad, check)

    def test_live_registry_declares_engine_code(self):
        from walter_platform import registry
        units, code = deploy.declared_services(registry.load())
        self.assertIn('dsh-web', units)
        self.assertTrue(any(p.endswith('ports/dsh') for p in code['dsh-web']['code_roots']))
        self.assertNotIn('walter-standby', units)   # timers are not long-running

    def test_core_guardian_may_restart_every_declared_service_and_nothing_else(self):
        from walter_platform import registry
        pb = json.loads((Path(__file__).resolve().parents[1] / 'guardian' / 'playbook.json').read_text())
        action = pb['actions']['restart_stale']
        self.assertEqual(action['command'], ['walter', 'deploy', 'restart', '{unit}'])
        self.assertEqual((action['level'], action['async']), ('G1', True))
        self.assertEqual(sorted(action['params']['unit']), sorted(deploy.declared_services(registry.load())[0]))
        self.assertEqual(pb['fallback']['deploy_stale']['action'], 'restart_stale')


if __name__ == '__main__':
    unittest.main()
