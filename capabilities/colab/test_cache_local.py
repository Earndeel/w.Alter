#!/usr/bin/env python3
"""Offline store-mode fixtures; no live Colab, Google auth, or network access.

Run local tests: python3 -B /opt/walter-colab/test_cache_local.py -v
Run untouched legacy suite against copied runtime: same command with --legacy.
Only fixture temp directories under TMPDIR are written by tests.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('cache_runtime.py')
LEGACY_TESTS = Path(__file__).parent / 'fixtures' / 'colab-cache-benchmark' / 'tests-cache-runtime.py'
APPROVED_STORE = '/content/walter-cache-store'
CACHE_ENV = 'WALTER_COLAB_CACHE_DIR'


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_runtime():
    return load_file('walter_cache_local_test_runtime', SCRIPT)


@contextmanager
def local_store_fixture(module, store):
    """Map only the approved Colab pathname to a REAL disposable filesystem.

    The VM is not Colab; mapping the pathname is the only path boundary mock.
    Directory checks, symlink checks, archive I/O, and checksums stay real.
    """
    def mapped_path(value):
        return store if str(value) == APPROVED_STORE else Path(value)
    with patch.dict(os.environ, {CACHE_ENV: APPROVED_STORE}), patch.object(module, 'Path', mapped_path):
        yield


class StoreModeTests(unittest.TestCase):
    def test_missing_or_nondirectory_local_store_is_rejected_without_creation(self):
        module = load_runtime()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing = root / 'missing'
            regular_file = root / 'not-a-directory'
            regular_file.write_bytes(b'OFFLINE_FIXTURE')
            for store in [missing, regular_file]:
                with self.subTest(store=store), local_store_fixture(module, store):
                    with self.assertRaisesRegex(module.CacheAbort, 'directory must already exist'):
                        module.require_store()
            self.assertFalse(missing.exists())
            self.assertEqual(regular_file.read_bytes(), b'OFFLINE_FIXTURE')

    def test_explicit_local_store_accepts_regular_directory_without_mount_or_google_auth(self):
        module = load_runtime()
        self.assertTrue(callable(getattr(module, 'require_store', None)),
                        'Explicit local-store guard is missing')
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / 'store'
            store.mkdir()
            google_before = {name for name in sys.modules if name.startswith('google')}
            with local_store_fixture(module, store), \
                    patch.object(Path, 'is_mount', side_effect=AssertionError('Local mode checked a mount')), \
                    patch.object(module, 'require_drive', side_effect=AssertionError('Local mode used Drive')):
                self.assertEqual(module.require_store(), store)
            self.assertEqual({name for name in sys.modules if name.startswith('google')}, google_before)

    def test_nonapproved_env_path_is_rejected_without_normalizing_it(self):
        module = load_runtime()
        with tempfile.TemporaryDirectory() as td:
            alternate = Path(td) / 'alternate'
            alternate.mkdir()
            for value in [str(alternate), '', APPROVED_STORE + '/',
                          '/content/./walter-cache-store', '/content/x/../walter-cache-store']:
                with self.subTest(value=value), patch.dict(os.environ, {CACHE_ENV: value}):
                    with self.assertRaisesRegex(module.CacheAbort, 'exactly /content/walter-cache-store'):
                        module.require_store()

    def test_local_store_rejects_symlink_directory_or_parent(self):
        module = load_runtime()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            actual = root / 'actual'
            actual.mkdir()
            (actual / 'child').mkdir()
            link = root / 'linked-store'
            link.symlink_to(actual, target_is_directory=True)
            for store in [link, link / 'child']:
                with self.subTest(store=store), local_store_fixture(module, store):
                    with self.assertRaisesRegex(module.CacheAbort, 'symlink'):
                        module.require_store()

    def test_absent_env_preserves_legacy_drive_directory_and_mount_guard(self):
        module = load_runtime()
        self.assertEqual(str(module.DRIVE), '/content/drive/MyDrive/W.Alter Colab Cache')
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ):
            os.environ.pop(CACHE_ENV, None)
            root = Path(td)
            module.DRIVE_MOUNT = root / 'drive'
            module.DRIVE = module.DRIVE_MOUNT / 'MyDrive' / 'W.Alter Colab Cache'
            module.DRIVE.mkdir(parents=True)
            with patch.object(Path, 'is_mount', return_value=True):
                try:
                    store = module.require_store()
                except Exception as error:
                    self.fail('Absent env did not select legacy Drive: ' + type(error).__name__)
                self.assertEqual(store, module.DRIVE)
            with patch.object(Path, 'is_mount', return_value=False):
                with self.assertRaisesRegex(module.CacheAbort, 'Google Drive must already be mounted'):
                    module.require_store()
            actual = root / 'actual'
            actual.mkdir()
            module.DRIVE.rmdir()
            module.DRIVE.symlink_to(actual, target_is_directory=True)
            with patch.object(Path, 'is_mount', return_value=True):
                with self.assertRaises(module.CacheAbort):
                    module.require_store()


class LocalWorkflowTests(unittest.TestCase):
    def test_local_restore_rejects_incompatible_base_before_copy_or_workspace_creation(self):
        import time
        with self.built_fixture() as (module, original, store, root, build_report):
            module.BENCH = root / 'incompatible-bench'
            module.COMFY = root / 'incompatible-codework' / 'ComfyUI'
            manifest = module.read_manifest(store / module.MANIFEST_NAME)
            module.preflight_original = lambda *args: {**manifest['base_before'], 'torch': 'INCOMPATIBLE'}
            module.copy_and_verify = lambda *args: self.fail('Copied before compatibility guard')
            with self.assertRaisesRegex(module.CacheAbort, 'Incompatible Colab base: torch'):
                module.restore_cache({'timings_seconds': {}}, time.perf_counter())
            self.assertFalse(module.BENCH.exists())
            self.assertFalse(module.COMFY.exists())

    def test_local_build_never_overwrites_existing_store_archive(self):
        with self.built_fixture() as (module, original, store, root, build_report):
            module.BENCH = root / 'second-build-bench'
            module.COMFY = root / 'second-build-codework' / 'ComfyUI'
            before = (store / module.ARCHIVE_NAME).read_bytes()
            with self.assertRaisesRegex(module.CacheAbort, 'never overwrite'):
                module.build_cache({'timings_seconds': {}})
            self.assertEqual((store / module.ARCHIVE_NAME).read_bytes(), before)
            self.assertFalse(module.BENCH.exists())

    @contextmanager
    def built_fixture(self):
        """Run REAL build/archive/copy/hash helpers; mock only GPU/setup boundaries."""
        import types
        module = load_runtime()
        legacy = load_file('walter_legacy_fixture_helpers', LEGACY_TESTS)
        legacy.SCRIPT = SCRIPT
        original_source, context = legacy.WorkflowContractTests().fixture_manifest(module)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            site = root / 'site-packages'
            site.mkdir()
            def install(name, version):
                info = site / (name + '-' + version + '.dist-info')
                info.mkdir()
                (info / 'METADATA').write_text('Metadata-Version: 2.1\nName: ' + name + '\nVersion: ' + version + '\n')
                (site / (name + '.py')).write_text('OFFLINE_FIXTURE = True\n')
                (info / 'RECORD').write_text(name + '.py,,\n' + info.name + '/METADATA,,\n' + info.name + '/RECORD,,\n')
            for name, version in [('torch', '2.8.0'), ('torchvision', '0.23.0'), ('numpy', '2.0.0')]:
                install(name, version)
            store = root / 'local-store'
            store.mkdir()
            module.BENCH = root / 'build-bench'
            module.COMFY = root / 'build-codework' / 'ComfyUI'
            module.GGUF = module.COMFY / 'custom_nodes' / 'ComfyUI-GGUF'
            module.require_colab = lambda: None  # VM is not an interactive Colab runtime.
            def setup(framework, *, skip_setup):
                self.assertFalse(skip_setup)
                install('offline-dependency', '1.0')
            original = types.SimpleNamespace(
                request_manifest=original_source.request_manifest, WORK=module.COMFY.parent,
                OUTPUT_PNG=root / 'output.png', RESULT_JSON=root / 'inference.json',
                COMFY_REVISION=original_source.COMFY_REVISION, GGUF_REVISION=original_source.GGUF_REVISION,
                setup_dependencies=setup, WIDTH=1, HEIGHT=1)
            module.load_original = lambda: original
            module.preflight_original = lambda *args: dict(context['base_before'])
            real_snapshot = module.snapshot_distributions
            module.snapshot_distributions = lambda: real_snapshot([site])
            module.repository_sources = lambda path, prefix, *args: {prefix + '/fixture.py': b'OFFLINE_CODE_FIXTURE = True\n'}
            module.run_subprocess = lambda mode, **kwargs: {
                'status': 'success', 'packages': {'torch': '2.8.0', 'torchvision': '0.23.0'}}
            with local_store_fixture(module, store), \
                    patch.object(Path, 'is_mount', side_effect=AssertionError('Local workflow checked mount')), \
                    patch.object(module, 'require_drive', side_effect=AssertionError('Local workflow used Drive')):
                report = {'timings_seconds': {}}
                module.build_cache(report)
                yield module, original, store, root, report

    def test_local_build_copies_real_archive_and_reports_local_not_drive_readback(self):
        with self.built_fixture() as (module, original, store, root, report):
            manifest = module.read_manifest(store / module.MANIFEST_NAME)
            self.assertEqual(module.sha256_file(store / module.ARCHIVE_NAME), manifest['archive']['sha256'])
            self.assertEqual(report['storage_mode'], 'local_staging')
            self.assertEqual(report['cache_store_path'], str(store))
            self.assertEqual(manifest['storage_mode'], 'local_staging')
            self.assertEqual(manifest['archive']['store_path'], str(store / module.ARCHIVE_NAME))
            self.assertTrue(report['local_store_sha256_independent_readback_verified'])
            self.assertNotIn('drive_sha256_independent_readback_verified', report)
            self.assertNotIn('drive_path', manifest['archive'])
            self.assertEqual(report['manifest_store_path'], str(store / module.MANIFEST_NAME))
            for phase in ['local_store_copy', 'local_store_verification', 'local_store_manifest_copy_and_verification']:
                self.assertIn(phase, report['timings_seconds'])

    def test_local_restore_reads_staged_archive_and_securely_extracts_without_drive(self):
        import hashlib
        import struct
        import time
        import zlib
        with self.built_fixture() as (module, original, store, root, build_report):
            module.BENCH = root / 'restore-bench'
            module.COMFY = root / 'restore-codework' / 'ComfyUI'
            module.OVERLAY = module.BENCH / 'packages'
            def chunk(kind, data):
                return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
            png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
                   + chunk(b'IDAT', zlib.compress(b'\x00\x01\x02\x03')) + chunk(b'IEND', b''))
            def infer(mode, **kwargs):
                self.assertEqual(mode, 'infer')
                self.assertTrue((module.COMFY / 'fixture.py').is_file())
                self.assertTrue((module.OVERLAY / 'offline-dependency.py').is_file())
                original.OUTPUT_PNG.write_bytes(png)
                return {
                    'bootstrap_seconds': 0, 'child_wall_seconds': 0, 'total_until_png_observed_seconds': 0,
                    'original_timings_seconds': {name: 0 for name in [
                        'dependencies', 'model_download_and_hash', 'text_encode', 'diffusion_load',
                        'sampling', 'vae_decode', 'export_png']},
                    'output': {'sha256': hashlib.sha256(png).hexdigest(), 'size_bytes': len(png),
                               'width': 1, 'height': 1, 'image_count': 1}}
            module.run_subprocess = infer  # No real GPU, model download, or inference in this offline fixture.
            report = {'timings_seconds': {}}
            module.restore_cache(report, time.perf_counter())
            self.assertEqual(report['storage_mode'], 'local_staging')
            self.assertEqual(report['cache_store_path'], str(store))
            self.assertIn('local_store_copy', report['timings_seconds'])
            self.assertNotIn('drive_copy', report['timings_seconds'])
            self.assertNotIn('drive_sha256_independent_readback_verified', report)
            self.assertEqual(module.sha256_file(module.BENCH / module.ARCHIVE_NAME),
                             module.sha256_file(store / module.ARCHIVE_NAME))
            self.assertEqual(report['output']['sha256'], hashlib.sha256(png).hexdigest())


class CliModeTests(unittest.TestCase):
    def test_cli_rejects_invalid_store_before_writes_or_dispatch(self):
        import io
        from contextlib import redirect_stderr
        module = load_runtime()
        module.require_colab = lambda: None
        module.build_cache = lambda *args: self.fail('Dispatched before validating store')
        module.restore_cache = lambda *args: self.fail('Dispatched before validating store')
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {CACHE_ENV: td}):
            module.BUILD_JSON = Path(td) / 'build.json'
            module.RESTORE_JSON = Path(td) / 'restore.json'
            for mode in ['build', 'restore']:
                with self.subTest(mode=mode), redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(module.main([mode]), 2)
                    self.assertIn('must be exactly /content/walter-cache-store', errors.getvalue())
            self.assertFalse(module.BUILD_JSON.exists())
            self.assertFalse(module.RESTORE_JSON.exists())

    def test_cli_dispatch_and_summary_report_local_storage_without_drive(self):
        import io
        import json
        from contextlib import redirect_stdout
        module = load_runtime()
        module.require_colab = lambda: None
        calls = []
        module.build_cache = lambda report: calls.append('build')
        module.restore_cache = lambda report, started: calls.append('restore')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = root / 'store'
            store.mkdir()
            module.BUILD_JSON = root / 'build.json'
            module.RESTORE_JSON = root / 'restore.json'
            with local_store_fixture(module, store), \
                    patch.object(module, 'require_drive', side_effect=AssertionError('CLI used Drive')):
                for mode, target in [('build', module.BUILD_JSON), ('restore', module.RESTORE_JSON)]:
                    with self.subTest(mode=mode), redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(module.main([mode]), 0)
                        report = json.loads(target.read_text())
                        summary = json.loads(output.getvalue().strip().split('=', 1)[1])
                        self.assertEqual(report['storage_mode'], 'local_staging')
                        self.assertEqual(report['cache_store_path'], str(store))
                        self.assertEqual(summary['storage_mode'], 'local_staging')
                        self.assertEqual(summary['cache_store_path'], str(store))
            self.assertEqual(calls, ['build', 'restore'])


def run_legacy_tests():
    suite_module = load_file('walter_untouched_legacy_cache_tests', LEGACY_TESTS)
    # ROOT remains the original fixture root; ONLY the target runtime changes.
    suite_module.SCRIPT = SCRIPT
    with patch.dict(os.environ):
        os.environ.pop(CACHE_ENV, None)
        suite = unittest.defaultTestLoader.loadTestsFromModule(suite_module)
        print(f'LEGACY_TARGET={suite_module.SCRIPT}', flush=True)
        print(f'LEGACY_TEST_COUNT={suite.countTestCases()}', flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    if '--legacy' in sys.argv:
        raise SystemExit(run_legacy_tests())
    unittest.main()
