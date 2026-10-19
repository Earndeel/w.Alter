"""Offline ONLY: invoke this file explicitly; never discover the legacy LIVE tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SCRATCH = Path(os.environ.get('TMPDIR', '/root/.hermes/cache/scratch'))


def load_cli():
    path = ROOT / 'on_demand.py'
    if not path.exists():
        raise AssertionError('on-demand CLI is not implemented')
    spec = importlib.util.spec_from_file_location('on_demand', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SpecTests(unittest.TestCase):
    def test_loads_and_pins_original_names_before_any_browser_action(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script = root / 'job.py'
            script.write_bytes(b"print('bonjour')\n")
            input_path = root / 'walter-probe.json'
            input_path.write_bytes(b'{"message":"bonjour"}')
            args = cli.parse_args(['job', str(script), '--input', str(input_path),
                                   '--output', 'result.json', '--result-dir', str(root / 'results')])
            spec = cli.prepare_job(args)
            self.assertEqual(spec.device, 'cpu')
            self.assertEqual(spec.timeout_seconds, 60)
            self.assertEqual(spec.script.name, 'job.py')
            self.assertEqual(spec.script.sha256, hashlib.sha256(script.read_bytes()).hexdigest())
            self.assertEqual(spec.inputs[0].name, 'walter-probe.json')
            self.assertEqual(spec.outputs, ('result.json',))
            self.assertEqual((root / 'results').stat().st_mode & 0o777, 0o700)

    def test_gpu_refusal_precedes_even_missing_script_or_directory_creation(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            result_dir = Path(root) / 'not-created'
            args = cli.parse_args(['job', str(Path(root) / 'missing.py'), '--device', 'T4',
                                   '--result-dir', str(result_dir)])
            with self.assertRaisesRegex(ValueError, 'allow-included-units'):
                cli.prepare_job(args)
            self.assertFalse(result_dir.exists())


    def test_validation_rejects_colliding_or_unsafe_names_and_symlinks(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script = root / 'job.py'
            script.write_text('pass\n')
            link = root / 'link.py'
            link.symlink_to(script)
            cases = [(['--output', 'job.py'], script),
                     (['--output', 'result.json', '--output', 'result.json'], script),
                     (['--input', str(script)], script),
                     (['--output', '../bad'], script),
                     (['--output', 'google_token.json'], script),
                     ([], link)]
            for flags, source in cases:
                with self.subTest(flags=flags, source=source), self.assertRaises(ValueError):
                    cli.prepare_job(cli.parse_args(['job', str(source), *flags, '--result-dir', str(root / 'results')]))
            result_dir = root / 'results'
            result_dir.mkdir(exist_ok=True)
            (result_dir / 'result.json').symlink_to(script)
            with self.assertRaises(ValueError):
                cli.prepare_job(cli.parse_args(['job', str(script), '--output', 'result.json', '--result-dir', str(result_dir)]))
            dir_link = root / 'dir-link'
            dir_link.symlink_to(result_dir, target_is_directory=True)
            with self.assertRaises(ValueError):
                cli.prepare_job(cli.parse_args(['job', str(script), '--result-dir', str(dir_link)]))

    def test_file_and_timeout_bounds_are_enforced_before_allocation(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script = root / 'job.py'
            script.write_bytes(b'x' * 5)
            with patch.object(cli, 'MAX_FILE', 4), self.assertRaises(ValueError):
                cli.load_file(script)
            script.write_bytes(b'')
            with self.assertRaises(ValueError):
                cli.load_file(script)
            script.write_text('pass\n')
            for timeout in (0, 3601):
                args = cli.parse_args(['job', str(script), '--timeout-seconds', str(timeout), '--result-dir', str(root / 'results')])
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    cli.prepare_job(args)
            for timeout in (1, 3600):
                spec = cli.prepare_job(cli.parse_args(['job', str(script), '--timeout-seconds', str(timeout), '--result-dir', str(root / 'results')]))
                self.assertEqual(spec.timeout_seconds, timeout)


class RemoteCodeTests(unittest.TestCase):
    def test_command_is_a_bounded_python_subprocess_without_shell_or_gpu_eval(self):
        cli = load_cli()
        script = cli.LocalFile(Path('/not-used/job.py'), 'job.py', 1, '0' * 64)
        spec = cli.JobSpec(script, (), (), 'T4', 60, Path('/not-used'))
        code = cli.job_code(spec)
        compile(code, '<remote-job>', 'exec')
        self.assertIn('subprocess.Popen(', code)
        self.assertIn('cwd=str(store)', code)
        self.assertIn('timeout=timeout_seconds', code)
        self.assertIn('start_new_session=True', code)
        self.assertIn('os.killpg(', code)
        self.assertIn('nvidia-smi', code)
        self.assertIn('--query-gpu=name', code)
        self.assertIn('re.search(', code)
        self.assertIn('WALTER_JOB_RESULT=', code)
        self.assertNotIn('eval(', code)
        self.assertNotIn('shell=True', code)
        self.assertNotIn('torch', code)

    def test_marker_is_unique_and_validated_not_source_text_or_unbounded_logs(self):
        cli = load_cli()
        report = {'status': 'success', 'exitcode': 0, 'stdout': 'bonjour', 'stderr': '', 'cell_seconds': 0.5}
        marker = 'WALTER_JOB_RESULT=' + json.dumps(report)
        self.assertEqual(cli.parse_job_result('noise\n' + marker), report)
        for text in ('no marker', marker + '\n' + marker,
                     'WALTER_JOB_RESULT=' + json.dumps(dict(report, stdout='x' * 8193)),
                     'WALTER_JOB_RESULT=' + json.dumps(dict(report, status='success', exitcode=1)),
                     'WALTER_JOB_RESULT=' + json.dumps(dict(report, cell_seconds=float('nan')))):
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                cli.parse_job_result(text)

    def test_cpu_cell_executes_locally_and_caps_stdout_without_any_notebook(self):
        import subprocess
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script_path = root / 'job.py'
            script_path.write_text("print('x' * 10000)\n")
            spec = cli.JobSpec(cli.load_file(script_path), (), (), 'cpu', 2, root)
            code = cli.job_code(spec).replace(repr(cli.transfer.STORE), repr(str(root)))
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                                    text=True, timeout=10, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            report = cli.parse_job_result(result.stdout)
            self.assertEqual(report['status'], 'success')
            self.assertEqual(len(report['stdout']), 8192)
            self.assertIsNone(report['gpu_names'])
            self.assertGreaterEqual(report['cell_seconds'], 0)

    def test_multibyte_stdout_is_bounded_in_utf8_bytes_not_only_characters(self):
        import subprocess
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script_path = root / 'job.py'
            script_path.write_text("print('é' * 10000)\n", encoding='utf-8')
            spec = cli.JobSpec(cli.load_file(script_path), (), (), 'cpu', 2, root)
            code = cli.job_code(spec).replace(repr(cli.transfer.STORE), repr(str(root)))
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                                    text=True, timeout=10, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            report = cli.parse_job_result(result.stdout)
            self.assertLessEqual(len(report['stdout'].encode('utf-8')), 8192)
        invalid = {'status': 'success', 'exitcode': 0, 'stdout': 'é' * 8192, 'stderr': '', 'cell_seconds': 0.5}
        with self.assertRaises(ValueError):
            cli.parse_job_result('WALTER_JOB_RESULT=' + json.dumps(invalid))

    def test_cpu_timeout_reports_failure_and_stops_child(self):
        import subprocess
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script_path = root / 'job.py'
            script_path.write_text("import time\nprint('started', flush=True)\ntime.sleep(20)\n")
            spec = cli.JobSpec(cli.load_file(script_path), (), (), 'cpu', 1, root)
            code = cli.job_code(spec).replace(repr(cli.transfer.STORE), repr(str(root)))
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                                    text=True, timeout=10, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            report = cli.parse_job_result(result.stdout)
            self.assertEqual(report['status'], 'timeout')
            self.assertIn('started', report['stdout'])
            self.assertNotEqual(report['exitcode'], 0)


class FakeBrowser:
    def __init__(self, events):
        self.events = events
        self.files = {}
        self.upload_error = False
        self.corrupt_download = False

    def assert_target(self):
        self.events.append('target')

    def upload(self, path):
        self.events.append('upload:' + Path(path).name)
        if self.upload_error:
            raise OSError('sensitive signed URL must not be logged')
        self.files[Path(path).name] = Path(path).read_bytes()

    def download(self, name, destination, *, expected_sha256, expected_size_bytes):
        self.events.append('download:' + name)
        blob = self.files[name]
        assert hashlib.sha256(blob).hexdigest() == expected_sha256
        assert len(blob) == expected_size_bytes
        Path(destination).write_bytes(b'corrupt' if self.corrupt_download else blob)


class FakeBridge:
    def __init__(self):
        self.events = []
        self.browser = FakeBrowser(self.events)
        self.state = {'disconnected': True, 'buttons': [], 'connection': []}
        self.initialize_error = False
        self.cleanup_error = False
        self.cleanup_connected = False
        self.selection = {'selected': 'cpu', 'disabled': False}
        self.job_status = 'success'
        self.job_error = False

    def connect(self):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def connection():
            self.events.append('connect')
            try:
                yield self
            finally:
                self.events.append('close')
        return connection()

    def runtime_state(self):
        self.events.append('state')
        return dict(self.state)

    def ensure_runtime_kind(self, device):
        self.events.append('select:' + device)
        return dict(self.selection)

    async def initialize(self):
        self.events.append('initialize')
        self.state['disconnected'] = False
        if self.initialize_error:
            raise RuntimeError('initialization could already have allocated')
        return {'drive_mounted': False, 'google_credentials_present': False}

    async def code(self, text, timeout=240):
        import ast
        if 'WALTER_JOB_FILE=' in text:
            name = next(ast.literal_eval(node.value) for node in ast.parse(text).body
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'name' for t in node.targets))
            data = self.browser.files.get(name)
            result = {'name': name, 'exists': data is not None}
            if data is not None:
                result.update(size=len(data), sha256=hashlib.sha256(data).hexdigest())
            return 'WALTER_JOB_FILE=' + json.dumps(result)
        self.events.append('job')
        self.job_timeout = timeout
        if self.job_error:
            raise TimeoutError('remote MCP exception; never rerun')
        self.browser.files['result.json'] = b'{"message":"bonjour"}'
        return 'WALTER_JOB_RESULT=' + json.dumps({'status': self.job_status,
                   'exitcode': 0 if self.job_status == 'success' else 1,
                   'stdout': 'bonjour', 'stderr': '', 'cell_seconds': 0.5, 'gpu_names': None})

    def delete_test_runtime(self):
        self.events.append('delete')
        if self.cleanup_error:
            raise RuntimeError('deletion failed')
        self.state['disconnected'] = not self.cleanup_connected
        return dict(self.state)


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_job_pins_upload_download_and_verifies_cleanup_before_success(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            script = root / 'job.py'
            script.write_text("print('bonjour')\n")
            input_path = root / 'walter-probe.json'
            input_path.write_text('{"message":"bonjour"}')
            args = cli.parse_args(['job', str(script), '--input', str(input_path),
                                   '--output', 'result.json', '--result-dir', str(root / 'results')])
            spec = cli.prepare_job(args)
            bridge = FakeBridge()
            report = await cli.run_prepared(spec, bridge)
            self.assertEqual(report['status'], 'success')
            self.assertEqual((spec.result_dir / 'result.json').read_bytes(), bridge.browser.files['result.json'])
            self.assertEqual(bridge.events.count('job'), 1)
            self.assertEqual(bridge.events.count('delete'), 1)
            self.assertLess(bridge.events.index('select:cpu'), bridge.events.index('initialize'))
            self.assertLess(bridge.events.index('initialize'), bridge.events.index('upload:job.py'))
            self.assertLess(bridge.events.index('download:result.json'), bridge.events.index('delete'))
            self.assertEqual(bridge.events[-3:], ['delete', 'state', 'close'])
            self.assertTrue(report['cleanup']['disconnected'])
            self.assertEqual(report['timings']['cell_seconds'], 0.5)
            self.assertGreaterEqual(report['timings']['total_seconds'], 0)
            self.assertIsNone(report['compute_units_consumed'])
            self.assertGreater(bridge.job_timeout, spec.timeout_seconds)


    async def test_initialization_failure_still_deletes_owned_attempt(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            bridge.initialize_error = True
            with self.assertRaises(cli.OnDemandError) as caught:
                await cli.run_prepared(spec, bridge)
            self.assertEqual(bridge.events.count('delete'), 1)
            self.assertNotIn('job', bridge.events)
            self.assertTrue(caught.exception.report['cleanup']['disconnected'])

    async def test_preexisting_or_ambiguous_state_is_never_deleted(self):
        for state in ({'disconnected': False}, {}, {'disconnected': True, 'connected': True}):
            cli, spec, bridge, temporary = self.make_job()
            with temporary:
                bridge.state = state
                with self.assertRaises(cli.OnDemandError):
                    await cli.run_prepared(spec, bridge)
                self.assertNotIn('initialize', bridge.events)
                self.assertNotIn('delete', bridge.events)

    async def test_unavailable_or_wrong_device_is_refused_before_ownership(self):
        for selection in ({'selected': 'T4', 'disabled': False}, {'selected': 'cpu', 'disabled': True},
                          {'selected': 'cpu', 'disabled': False, 'resources_before': {'active_sessions': 1}}):
            cli, spec, bridge, temporary = self.make_job()
            with temporary:
                bridge.selection = selection
                with self.assertRaises(cli.OnDemandError):
                    await cli.run_prepared(spec, bridge)
                self.assertNotIn('initialize', bridge.events)
                self.assertNotIn('delete', bridge.events)

    async def test_job_or_transfer_exception_cleans_once_without_rerunning(self):
        for failure in ('upload', 'job', 'corrupt_download'):
            cli, spec, bridge, temporary = self.make_job()
            with temporary:
                bridge.browser.upload_error = failure == 'upload'
                bridge.job_error = failure == 'job'
                bridge.browser.corrupt_download = failure == 'corrupt_download'
                with self.assertRaises(cli.OnDemandError) as caught:
                    await cli.run_prepared(spec, bridge)
                self.assertEqual(bridge.events.count('delete'), 1)
                self.assertEqual(bridge.events.count('connect'), 1)
                self.assertLessEqual(bridge.events.count('job'), 1)
                self.assertTrue(caught.exception.report['cleanup']['disconnected'])
                self.assertFalse((spec.result_dir / 'result.json').exists())
                self.assertNotIn('sensitive signed URL', json.dumps(caught.exception.report))

    async def test_error_or_timeout_job_returns_non_success_after_verified_cleanup(self):
        for status in ('error', 'timeout'):
            cli, spec, bridge, temporary = self.make_job()
            with temporary:
                bridge.job_status = status
                report = await cli.run_prepared(spec, bridge)
                self.assertEqual(report['status'], status)
                self.assertTrue(report['cleanup']['disconnected'])
                self.assertEqual(bridge.events.count('job'), 1)
                self.assertNotIn('download:result.json', bridge.events)

    async def test_cleanup_failure_overrides_success_and_preserves_primary_error(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            bridge.browser.upload_error = True
            bridge.cleanup_error = True
            with self.assertRaises(cli.CleanupError) as caught:
                await cli.run_prepared(spec, bridge)
            report = caught.exception.report
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['primary_error_type'], 'OSError')
            self.assertEqual(report['cleanup']['error_type'], 'RuntimeError')
            self.assertIsNotNone(report['timings']['total_seconds'])

    async def test_disconnected_toolbar_with_active_session_is_cleanup_failure(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            original = bridge.delete_test_runtime
            def unreleased():
                return dict(original(), resources_after={'active_sessions': 1})
            bridge.delete_test_runtime = unreleased
            with self.assertRaises(cli.CleanupError) as caught:
                await cli.run_prepared(spec, bridge)
            self.assertEqual(caught.exception.report['cleanup']['resources_after']['active_sessions'], 1)
            self.assertEqual(caught.exception.report['status'], 'error')

    async def test_report_keeps_resource_snapshots_without_inventing_consumption(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            before = {'compute_units': 5.0, 'active_sessions': 0, 'rate_text': 'test-double'}
            after = {'compute_units': 5.0, 'active_sessions': 0, 'rate_text': 'test-double'}
            bridge.selection['resources_before'] = before
            original = bridge.delete_test_runtime
            bridge.delete_test_runtime = lambda: dict(original(), resources_after=after)
            ticks = iter((100.0, 101.25))
            report = await cli.run_prepared(spec, bridge, clock=lambda: next(ticks))
            self.assertEqual(report['resources_before'], before)
            self.assertEqual(report['cleanup']['resources_after'], after)
            self.assertEqual(report['timings']['total_seconds'], 1.25)
            self.assertIsNone(report['compute_units_consumed'])

    async def test_identical_local_output_is_reused_and_nonidentical_is_not_overwritten(self):
        for contents in (b'{"message":"bonjour"}', b'old-result'):
            cli, spec, bridge, temporary = self.make_job()
            with temporary:
                destination = spec.result_dir / 'result.json'
                destination.write_bytes(contents)
                if contents == b'old-result':
                    with self.assertRaises(cli.OnDemandError):
                        await cli.run_prepared(spec, bridge)
                else:
                    report = await cli.run_prepared(spec, bridge)
                    self.assertTrue(report['outputs'][0]['already_present'])
                self.assertEqual(destination.read_bytes(), contents)
                self.assertNotIn('download:result.json', bridge.events)
                self.assertEqual(bridge.events.count('delete'), 1)

    async def test_sources_changed_since_preload_are_not_uploaded(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            spec.script.path.write_text('changed\n')
            with self.assertRaises(cli.OnDemandError):
                await cli.run_prepared(spec, bridge)
            self.assertNotIn('upload:job.py', bridge.events)
            self.assertEqual(bridge.events.count('delete'), 1)

    async def test_nonidentical_remote_upload_collision_is_not_overwritten(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            bridge.browser.files['job.py'] = b'unrelated runtime file'
            with self.assertRaises(cli.OnDemandError):
                await cli.run_prepared(spec, bridge)
            self.assertEqual(bridge.browser.files['job.py'], b'unrelated runtime file')
            self.assertNotIn('upload:job.py', bridge.events)
            self.assertEqual(bridge.events.count('delete'), 1)

    async def test_successful_job_with_connected_cleanup_is_failure(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            bridge.cleanup_connected = True
            with self.assertRaises(cli.CleanupError) as caught:
                await cli.run_prepared(spec, bridge)
            self.assertEqual(caught.exception.report['job']['status'], 'success')
            self.assertEqual(caught.exception.report['status'], 'error')
            self.assertFalse(caught.exception.report['cleanup']['disconnected'])

    async def test_racing_destination_disappearing_cannot_claim_published_output(self):
        cli, spec, bridge, temporary = self.make_job()
        with temporary, patch.object(cli.os, 'link', side_effect=FileExistsError):
            with self.assertRaises(cli.OnDemandError):
                await cli.run_prepared(spec, bridge)
            self.assertFalse((spec.result_dir / 'result.json').exists())
            self.assertEqual(bridge.events.count('delete'), 1)

    async def test_cancellation_after_ownership_still_cleans_up(self):
        import asyncio
        cli, spec, bridge, temporary = self.make_job()
        with temporary:
            async def cancelled_initialize():
                bridge.state['disconnected'] = False
                raise asyncio.CancelledError()
            bridge.initialize = cancelled_initialize
            with self.assertRaises(asyncio.CancelledError):
                await cli.run_prepared(spec, bridge)
            self.assertEqual(bridge.events.count('delete'), 1)

    def make_job(self):
        cli = load_cli()
        temporary = tempfile.TemporaryDirectory(dir=SCRATCH)
        root = Path(temporary.name)
        script = root / 'job.py'
        script.write_text("print('bonjour')\n")
        args = cli.parse_args(['job', str(script), '--output', 'result.json', '--result-dir', str(root / 'results')])
        return cli, cli.prepare_job(args), FakeBridge(), temporary


class CliTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_offline_cli_flow_executes_actual_smoke_script_and_metadata_cells(self):
        import shutil
        import subprocess
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            local_runtime = root / 'offline-runtime'
            local_runtime.mkdir()
            bridge = FakeBridge()
            def upload(path):
                shutil.copyfile(path, local_runtime / Path(path).name)
            def download(name, destination, **pins):
                shutil.copyfile(local_runtime / name, destination)
            bridge.browser.upload = upload
            bridge.browser.download = download
            async def code(text, timeout=240):
                import asyncio
                text = text.replace(repr(cli.transfer.STORE), repr(str(local_runtime)))
                result = await asyncio.to_thread(subprocess.run, [sys.executable, '-B', '-c', text],
                    capture_output=True, text=True, timeout=timeout,
                    env=dict(os.environ, PATH='', PYTHONDONTWRITEBYTECODE='1'))
                if result.returncode:
                    raise AssertionError(result.stderr)
                return result.stdout
            bridge.code = code
            input_path = root / 'walter-probe.json'
            input_path.write_text('{"message":"bonjour"}')
            args = cli.parse_args(['job', str(ROOT / 'fixtures/on-demand-cpu-smoke.py'),
                '--input', str(input_path), '--output', 'result.json', '--result-dir', str(root / 'results')])
            report = await cli.execute(args, config={'browser_session': 'offline', 'notebook_id': 'offline'},
                browser_factory=lambda *_: bridge.browser, bridge_factory=lambda _: bridge)
            actual = json.loads((root / 'results/result.json').read_text())
            self.assertEqual(actual['message'], 'bonjour')
            self.assertEqual(actual['device'], 'cpu')
            self.assertEqual(report['status'], 'success')
            self.assertTrue(report['cleanup']['disconnected'])
            self.assertEqual(bridge.events.count('delete'), 1)
            self.assertEqual(report['outputs'][0]['sha256'], hashlib.sha256((root / 'results/result.json').read_bytes()).hexdigest())

    async def test_execute_validates_before_browser_construction(self):
        cli = load_cli()
        args = cli.parse_args(['job', '/not-present/job.py', '--device', 'T4', '--result-dir', '/not-present/results'])
        def forbidden(*args):
            self.fail('Invalid spec must not construct a browser')
        with self.assertRaisesRegex(ValueError, 'allow-included-units'):
            await cli.execute(args, config={}, browser_factory=forbidden)

    def test_main_prints_json_and_nonzero_for_timeout_without_raw_exception(self):
        import contextlib
        import io
        from unittest.mock import AsyncMock
        cli = load_cli()
        args = ['job', '/not-used/job.py', '--result-dir', '/not-used/results']
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, 'execute', AsyncMock(return_value={'status': 'timeout'})), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(cli.main(args), 1)
        self.assertEqual(json.loads(stdout.getvalue())['status'], 'timeout')
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, 'execute', AsyncMock(side_effect=RuntimeError('SECRET-signed-url'))), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(cli.main(args), 1)
        self.assertNotIn('SECRET', stderr.getvalue())
        self.assertEqual(json.loads(stderr.getvalue())['error_type'], 'RuntimeError')


class FixtureTests(unittest.TestCase):
    def test_fixture_runs_offline_cpu_and_echoes_input_and_actual_platform(self):
        import platform
        import subprocess
        fixture = ROOT / 'fixtures/on-demand-cpu-smoke.py'
        self.assertTrue(fixture.exists(), 'CPU smoke fixture is missing')
        self.assertNotIn('import torch', fixture.read_text())
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
            root = Path(root)
            (root / 'walter-probe.json').write_text('{"message":"bonjour"}')
            result = subprocess.run([sys.executable, '-B', str(fixture)], cwd=root,
                                    env=dict(os.environ, PATH='', PYTHONDONTWRITEBYTECODE='1'),
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'result.json').read_text())
            self.assertEqual(report['message'], 'bonjour')
            self.assertEqual(report['device'], 'cpu')
            self.assertFalse(report['nvidia_smi_present'])
            self.assertEqual(report['machine'], platform.machine())
            self.assertEqual(report['python_version'], platform.python_version())


if __name__ == '__main__':
    unittest.main()
