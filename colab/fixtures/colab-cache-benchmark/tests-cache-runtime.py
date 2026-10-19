#!/usr/bin/env python3
"""Offline fixtures only. Never a Colab benchmark or GPU execution."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
import tarfile
import io
import hashlib
import json
import os
import struct
import zlib

SCRATCH = Path('/root/.hermes/cache/scratch')

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "cache_runtime.py"


def load_runtime():
    spec = importlib.util.spec_from_file_location("cache_runtime", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ImportSafetyTests(unittest.TestCase):
    def test_import_has_no_network_gpu_process_or_file_writes(self):
        self.assertTrue(SCRIPT.is_file(), "cache_runtime.py has not been implemented")
        probe = r'''
import importlib.util, sys
path = sys.argv[1]
def audit(event, args):
    if event in ('socket.connect', 'socket.bind', 'subprocess.Popen', 'os.system'):
        raise AssertionError('Import side effect: '+event)
    if event == 'open' and (isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or isinstance(args[2], int) and args[2] & 3):
        raise AssertionError('Import writes a file')
sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location('cache_runtime', path)
m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m
spec.loader.exec_module(m)
assert 'torch' not in sys.modules
assert 'numpy' not in sys.modules
assert 'huggingface_hub' not in sys.modules
print('IMPORT_SAFE_OFFLINE')
'''
        result = subprocess.run([sys.executable, "-B", "-c", probe, str(SCRIPT)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "IMPORT_SAFE_OFFLINE")


class ArchiveSafetyTests(unittest.TestCase):
    def test_archive_is_exact_regular_allowlisted_content_before_extraction(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'secure_extract', None)), 'Secure extraction missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            good = b'print("fixture only")\n'
            name = 'packages/demo/__init__.py'
            files = {name: {'size_bytes': len(good), 'sha256': hashlib.sha256(good).hexdigest()}}
            def make_tar(path, entries):
                with tarfile.open(path, 'w:gz', compresslevel=1) as tf:
                    for member_name, kind, data in entries:
                        entry = tarfile.TarInfo(member_name)
                        entry.type = kind
                        entry.size = len(data) if kind == tarfile.REGTYPE else 0
                        entry.linkname = '../../escaped'
                        tf.addfile(entry, io.BytesIO(data) if entry.isreg() else None)
            archive = root / 'good.tar.gz'
            make_tar(archive, [(name, tarfile.REGTYPE, good)])
            m.secure_extract(archive, root / 'good', files)
            self.assertEqual((root / 'good' / name).read_bytes(), good)
            bad_names = ['../escaped', '/absolute', 'packages/../../escaped',
                         'packages/./demo.py', 'packages//demo.py', 'packages\\evil.py',
                         'other/evil.py', 'packages/torch/evil.py', 'packages/nvidia/x.so',
                         'packages/a.pyc', 'packages/__pycache__/a', 'packages/.env',
                         'code/ComfyUI/models/bad.gguf', 'code/ComfyUI/models/bad.safetensors',
                         'code/ComfyUI/.git/hooks/post-checkout', 'code/ComfyUI/.git/objects/info/alternates']
            scenarios = [(n, tarfile.REGTYPE, good) for n in bad_names]
            scenarios += [(name, kind, good) for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE]]
            for index, entry in enumerate(scenarios):
                with self.subTest(entry=entry[:2]):
                    path = root / f'bad-{index}.tar.gz'
                    make_tar(path, [entry])
                    forged = {entry[0]: files[name]}
                    destination = root / f'extract-{index}'
                    with self.assertRaises(m.CacheAbort):
                        m.secure_extract(path, destination, forged)
                    self.assertFalse(destination.exists())
            for entries, inventory in [([(name, tarfile.REGTYPE, good)]*2, files),
                                       ([(name, tarfile.REGTYPE, good)], {}),
                                       ([(name, tarfile.REGTYPE, b'tampered')], files),
                                       ([], files)]:
                path = root / 'mismatch.tar.gz'
                make_tar(path, entries)
                with self.assertRaises(m.CacheAbort):
                    m.secure_extract(path, root / 'mismatch', inventory)
            target = root / 'linktarget'
            target.mkdir()
            (root / 'destlink').symlink_to(target, target_is_directory=True)
            with self.assertRaises(m.CacheAbort):
                m.secure_extract(archive, root / 'destlink', files)


class CompatibilityTests(unittest.TestCase):
    def test_incompatible_base_is_rejected_before_any_copy(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'check_compatibility', None)), 'Compatibility guard missing')
        base = {'machine': 'x86_64', 'system': 'Linux', 'python_abi': 'cpython-312-x86_64-linux-gnu',
                'python_major_minor': [3, 12], 'python_version': '3.12.1',
                'torch': '2.8.0+cu126', 'torchvision': '0.23.0+cu126',
                'cuda': '12.6', 'numpy': '2.0.0'}
        m.check_compatibility(base, dict(base), [])
        newer = {**base, 'python_version': '3.12.9', 'numpy': '2.2.0'}
        m.check_compatibility(base, newer, ['numpy'])
        for key in ['machine', 'system', 'python_abi', 'python_major_minor', 'torch', 'torchvision', 'cuda', 'numpy']:
            with self.subTest(key=key):
                with self.assertRaises(m.CacheAbort):
                    m.check_compatibility(base, {**base, key: 'different'}, [])
        for key in ['torch', 'torchvision', 'cuda']:
            with self.assertRaises(m.CacheAbort):
                m.check_compatibility(base, {**base, key: 'different'}, [key])
        with self.assertRaises(m.CacheAbort):
            m.check_compatibility({}, {}, [])

    def test_cli_refuses_vm_without_side_effects(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'main', None)), 'Colab-only CLI missing')
        for mode in ['build', 'restore']:
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), mode],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('Colab', result.stderr)
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--help'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('build', result.stdout)
        self.assertIn('restore', result.stdout)

    def test_restore_process_allowlist_rejects_installers_and_git_network(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'check_child_command', None)), 'Restore command guard missing')
        for args in [['git', 'rev-parse', 'HEAD'], ['git', 'remote', 'get-url', 'origin'],
                     ['git', '-c', 'credential.helper=', 'status', '--porcelain', '--untracked-files=no'],
                     ['nvidia-smi', '--query-gpu=name,uuid,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits']]:
            m.check_child_command(args)
        for args in [['pip', 'install', 'x'], [sys.executable, '-m', 'pip', 'install', 'x'],
                     ['git', 'fetch', 'origin'], ['git', 'clone', 'https://example.test'],
                     ['git', 'remote', 'add', 'origin', 'https://example.test'],
                     ['git', '-c', 'core.fsmonitor=evil', 'status', '--porcelain', '--untracked-files=no'],
                     ['sh', '-c', 'pip install x'], ['uv', 'pip', 'install', 'x']]:
            with self.subTest(args=args):
                with self.assertRaises(m.CacheAbort):
                    m.check_child_command(args)


class DistributionArchiveTests(unittest.TestCase):
    def test_delta_uses_versions_and_record_hash_and_keeps_only_site_files(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'snapshot_distributions', None)), 'Distribution snapshot missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            site = root / 'site-packages'
            site.mkdir()
            def install(name, version, extra=''):
                info = site / (name + '-' + version + '.dist-info')
                info.mkdir(exist_ok=True)
                (info / 'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+'\n')
                (info / 'WHEEL').write_text('Wheel-Version: 1.0\n')
                (site / (name + '.py')).write_text('VALUE = "fixture"\n')
                rows = [name+'.py', info.name+'/METADATA', info.name+'/WHEEL', info.name+'/RECORD']
                if extra:
                    (site / (name+'_extra.py')).write_text(extra)
                    rows.append(name+'_extra.py')
                (info / 'RECORD').write_text(''.join(p+',,\n' for p in rows)+
                                            '../bin/demo,,\n'+name+'.pyc,,\n')
                (site / (name+'.pyc')).write_bytes(b'bytecode fixture')
            install('torch', '2.8.0')
            install('old', '1.0')
            install('same', '1.0')
            before = m.snapshot_distributions([site])
            install('same', '1.0', 'CHANGED = True\n')
            install('new', '2.0')
            after = m.snapshot_distributions([site])
            changed = m.changed_distributions(before, after)
            self.assertEqual(set(changed), {'same', 'new'})
            self.assertNotEqual(before['same']['record_sha256'], after['same']['record_sha256'])
            sources, packages, skipped = m.package_sources(changed, after)
            self.assertIn('packages/same-1.0.dist-info/RECORD', sources)
            self.assertIn('packages/new-2.0.dist-info/METADATA', sources)
            self.assertNotIn('packages/old.py', sources)
            self.assertFalse(any('torch' in n or n.endswith('.pyc') or '/bin/' in n for n in sources))
            self.assertGreater(skipped['outside_site_packages'], 0)
            archive = root / 'delta.tar.gz'
            inventory = m.write_archive(archive, sources)
            m.secure_extract(archive, root / 'extracted', inventory)
            versions = {d.metadata['Name']: d.version for d in __import__('importlib.metadata', fromlist=['']).distributions(path=[str(root/'extracted'/'packages')])}
            self.assertEqual(versions, {'same':'1.0', 'new':'2.0'})
            # Real file copy + real independent checksum; no Drive/network use.
            copied = root / 'copy.tar.gz'
            m.copy_and_verify(archive, copied, m.sha256_file(archive))
            self.assertEqual(copied.read_bytes(), archive.read_bytes())
            with self.assertRaises(m.CacheAbort):
                m.copy_and_verify(archive, root / 'badcopy.tar.gz', '0'*64)
            modified = {k:dict(v) for k,v in after.items()}
            modified['torch']['record_sha256'] = '0'*64
            with self.assertRaises(m.CacheAbort):
                m.changed_distributions(before, modified)
            (site / 'new.py').unlink()
            (site / 'new.py').symlink_to(root / 'outside-secret')
            (root / 'outside-secret').write_text('must not be read')
            with self.assertRaises(m.CacheAbort):
                m.package_sources(changed, after)


class CodeAndOverlayTests(unittest.TestCase):
    def test_local_git_code_archive_strips_credentials_and_untracked_files(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'repository_sources', None)), 'Code archive collector missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            repo = root / 'repo'
            repo.mkdir()
            env = {**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null'}
            def git(*args, cwd=repo):
                p = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(p.returncode, 0, p.stderr)
                return p.stdout.strip()
            git('init', '-q')
            git('config', 'user.name', 'Offline fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (repo / 'node.py').write_text('NODE = "fixture"\n')
            git('add', 'node.py')
            git('commit', '-qm', 'offline fixture')
            rev = git('rev-parse', 'HEAD')
            url = 'https://example.invalid/public.git'
            git('remote', 'add', 'origin', url)
            git('config', 'http.extraHeader', 'SENSITIVE-FIXTURE-DO-NOT-ARCHIVE')
            (repo / '.env').write_text('UNTRACKED_SECRET_FIXTURE')
            (repo / 'model.gguf').write_bytes(b'UNTRACKED_WEIGHT_FIXTURE')
            sources = m.repository_sources(repo, 'code/ComfyUI', rev, url)
            self.assertNotIn('code/ComfyUI/.env', sources)
            self.assertFalse(any('model.gguf' in k for k in sources))
            self.assertNotIn(b'SENSITIVE-FIXTURE', sources['code/ComfyUI/.git/config'])
            archive = root / 'code.tar.gz'
            files = m.write_archive(archive, sources)
            m.secure_extract(archive, root / 'extracted', files)
            restored = root / 'extracted' / 'code' / 'ComfyUI'
            self.assertEqual(git('rev-parse', 'HEAD', cwd=restored), rev)
            self.assertEqual(git('remote', 'get-url', 'origin', cwd=restored), url)
            self.assertEqual(git('status', '--porcelain', '--untracked-files=no', cwd=restored), '')
            (repo / 'node.py').write_text('MODIFIED = True\n')
            with self.assertRaises(m.CacheAbort):
                m.repository_sources(repo, 'code/ComfyUI', rev, url)

    def test_overlay_processes_pth_then_reprios_and_checks_distribution_provenance(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'activate_overlay', None)), 'Overlay activation missing')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            overlay = root / 'packages'
            overlay.mkdir()
            (overlay / 'extra').mkdir()
            (overlay / 'hook.pth').write_text('extra\nimport sys; sys.path.insert(0, "pth-hijack-fixture")\n')
            info = overlay / 'demo-1.0.dist-info'
            info.mkdir()
            (info / 'METADATA').write_text('Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n')
            (info / 'RECORD').write_text('demo-1.0.dist-info/METADATA,,\n')
            spec = {'name':'demo', 'version':'1.0', 'overlay_metadata_dir': info.name,
                    'record_sha256':hashlib.sha256((info/'RECORD').read_bytes()).hexdigest()}
            probe = '''import importlib.util,sys,json\ns=importlib.util.spec_from_file_location('cache_runtime',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nm.activate_overlay(m.Path(sys.argv[2])); assert sys.path[0]==sys.argv[2]; assert str(m.Path(sys.argv[2])/'extra') in sys.path\nm.verify_overlay([json.loads(sys.argv[3])],m.Path(sys.argv[2])); print('PTH_OVERLAY_OK')'''
            p = subprocess.run([sys.executable, '-B', '-c', probe, str(SCRIPT), str(overlay), json.dumps(spec)], capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.strip(), 'PTH_OVERLAY_OK')
            spec['version'] = '9.9'
            p = subprocess.run([sys.executable, '-B', '-c', probe, str(SCRIPT), str(overlay), json.dumps(spec)], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('CacheAbort', p.stderr)


class OriginalAndOutputTests(unittest.TestCase):
    def test_original_is_hash_pinned_and_only_setup_is_patched_with_models_allowed(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'load_original', None)), 'Original script loader missing')
        source = ROOT.parent / 'colab-qwen-image-test' / 'runtime_inference.py'
        original = m.load_original(source)
        self.assertEqual(m.sha256_file(source), m.ORIGINAL_SHA256)
        request = original.request_manifest()
        self.assertEqual(request['parameters']['steps'], 25)
        self.assertEqual(request['parameters']['seed'], 42)
        self.assertEqual(request['parameters']['cfg'], 2.0)
        self.assertEqual(request['parameters']['width'], 1024)
        self.assertEqual(request['parameters']['height'], 1024)
        import types
        calls = []
        def setup(framework, *, skip_setup):
            calls.append(('setup', skip_setup, framework))
        stub = types.SimpleNamespace(setup_dependencies=setup)
        marker = object()
        stub.prepare_models = marker
        def main(args):
            calls.append(('main', args))
            stub.setup_dependencies({'torch': 'fixture'}, skip_setup=False)
            return 0
        stub.main = main
        self.assertEqual(m.call_original_no_install(stub), 0)
        self.assertEqual(calls, [('main', []), ('setup', True, {'torch':'fixture'})])
        self.assertIs(stub.main, main)
        self.assertIs(stub.prepare_models, marker)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            modified = Path(td)/'modified.py'
            modified.write_text(source.read_text()+'\n# changed\n')
            with self.assertRaises(m.CacheAbort):
                m.load_original(modified)

    def test_png_hash_geometry_crc_and_model_result_evidence_are_checked(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m, 'verify_png', None)), 'PNG validation missing')
        def chunk(kind, payload):
            return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
        raw = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x01\x02\x03'))+chunk(b'IEND',b'')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            png = Path(td)/'fixture.png'
            png.write_bytes(raw)
            spec = {'width':1,'height':1,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'image_count':1}
            result = m.verify_png(png, 1, 1, spec)
            self.assertEqual(result['sha256'], spec['sha256'])
            with self.assertRaises(m.CacheAbort):
                m.verify_png(png, 2, 1, spec)
            with self.assertRaises(m.CacheAbort):
                m.verify_png(png, 1, 1, {**spec,'sha256':'0'*64})
            png.write_bytes(raw[:-5]+b'broken')
            with self.assertRaises(m.CacheAbort):
                m.verify_png(png, 1, 1, spec)
            png.write_bytes(raw)
            request = {'model_revision':'fixture-revision', 'model_files':[{'repo_path':'a','local_path':'a','size':3,'sha256':'a'*64}], 'parameters':{'width':1,'height':1}}
            models = Path(td)/'models'
            models.mkdir()
            (models/'a').write_bytes(b'abc')
            evidence = {'status':'success', 'runtime_script_sha256':m.ORIGINAL_SHA256,
                        'model_revision':'fixture-revision',
                        'model_files_verified':[{'repo_path':'a','revision':'fixture-revision','size_bytes':3,'sha256':'a'*64,'path':str(models/'a')}],
                        'output':{**spec,'path':str(png)}}
            m.verify_inference_evidence(evidence, request, models, png)
            evidence['model_files_verified'][0]['sha256'] = '0'*64
            with self.assertRaises(m.CacheAbort):
                m.verify_inference_evidence(evidence, request, models, png)


class WorkflowContractTests(unittest.TestCase):
    def fixture_manifest(self, m):
        original = m.load_original(ROOT.parent / 'colab-qwen-image-test' / 'runtime_inference.py')
        request = original.request_manifest()
        base = {'machine':'x86_64','system':'Linux','python_abi':'cpython-312-x86_64-linux-gnu',
                'python_major_minor':[3,12],'python_version':'3.12.1','torch':'2.8.0','torchvision':'0.23.0',
                'cuda':'12.6','numpy':'2.0.0'}
        return original, {'schema':m.SCHEMA,'original_script_sha256':m.ORIGINAL_SHA256,
                          'cache_script_sha256':m.sha256_file(SCRIPT),'request':request,
                          'code_revisions':request['code_revisions'],
                          'base_before':base, 'base_after':dict(base),
                          'archive':{'filename':m.ARCHIVE_NAME,'sha256':'a'*64,'size_bytes':123,'compression_level':1},
                          'packages':[], 'files':{}, 'changed_distributions':[]}

    def test_manifest_rejects_mutated_source_settings_revisions_and_protected_overlay(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m,'validate_manifest',None)), 'Manifest identity validation missing')
        original, fixture = self.fixture_manifest(m)
        m.validate_manifest(fixture, original)
        for mutation in ['script','revision','parameter','archive','protected']:
            with self.subTest(mutation=mutation):
                bad = json.loads(json.dumps(fixture))
                if mutation == 'script': bad['original_script_sha256'] = '0'*64
                if mutation == 'revision': bad['code_revisions']['gguf'] = '0'*40
                if mutation == 'parameter': bad['request']['parameters']['steps'] = 1
                if mutation == 'archive': bad['archive']['filename'] = '../escape.tar.gz'
                if mutation == 'protected': bad['packages'] = [{'name':'nvidia-cublas-cu12'}]
                with self.assertRaises(m.CacheAbort):
                    m.validate_manifest(bad, original)

    def test_restore_checks_compatibility_before_copy_or_workspace_creation(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m,'restore_cache',None)), 'Restore workflow missing')
        import types
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            original, fixture = self.fixture_manifest(m)
            stub = types.SimpleNamespace(request_manifest=original.request_manifest,
                                         OUTPUT_PNG=root/'output.png', RESULT_JSON=root/'inference.json')
            m.BENCH = root/'bench'; m.COMFY = root/'code'; m.OVERLAY = m.BENCH/'packages'
            m.DRIVE = root/'drive'; m.DRIVE.mkdir()
            (m.DRIVE/m.MANIFEST_NAME).write_text(json.dumps(fixture))
            m.require_colab = lambda: None
            m.require_drive = lambda: None
            m.load_original = lambda: stub
            incompatible = {**fixture['base_before'],'torch':'DIFFERENT'}
            m.preflight_original = lambda original, report: incompatible
            m.copy_and_verify = lambda *a: self.fail('Copy started before compatibility guard')
            report = {'timings_seconds':{}}
            with self.assertRaises(m.CacheAbort):
                m.restore_cache(report, __import__('time').perf_counter())
            self.assertFalse(m.BENCH.exists())
            self.assertFalse(m.COMFY.exists())

    def test_fixture_build_exercises_archive_and_drive_readback_without_fake_archive_identity(self):
        m = load_runtime()
        import types
        original_source = m.load_original(ROOT.parent / 'colab-qwen-image-test' / 'runtime_inference.py')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            site = root/'site-packages'; site.mkdir()
            def install(name, version):
                info = site/(name+'-'+version+'.dist-info'); info.mkdir()
                (info/'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+'\n')
                (site/(name+'.py')).write_text('FIXTURE = True\n')
                (info/'RECORD').write_text(name+'.py,,\n'+info.name+'/METADATA,,\n'+info.name+'/RECORD,,\n')
            for name, version in [('torch','2.8.0'),('torchvision','0.23.0'),('numpy','2.0.0'),('triton','3.4.0'),('nvidia-cublas-cu12','12.8')]:
                install(name,version)
            m.BENCH=root/'bench'; m.DRIVE=root/'drive'; m.DRIVE.mkdir()
            m.COMFY=root/'codework'/'ComfyUI'; m.GGUF=m.COMFY/'custom_nodes'/'ComfyUI-GGUF'
            m.require_colab=lambda:None; m.require_drive=lambda:None
            base=self.fixture_manifest(m)[1]['base_before']
            calls=[]
            def setup(framework, *, skip_setup):
                calls.append((framework,skip_setup))
                install('newdependency','1.0')
            stub=types.SimpleNamespace(request_manifest=original_source.request_manifest,WORK=m.COMFY.parent,
                                       OUTPUT_PNG=root/'output.png',RESULT_JSON=root/'original-result.json',
                                       COMFY_REVISION=original_source.COMFY_REVISION,GGUF_REVISION=original_source.GGUF_REVISION,
                                       setup_dependencies=setup)
            m.load_original=lambda:stub
            m.preflight_original=lambda *a:dict(base)
            actual_snapshot=m.snapshot_distributions
            m.snapshot_distributions=lambda:actual_snapshot([site])
            m.repository_sources=lambda path,prefix,*args:{prefix+'/fixture.py':b'OFFLINE_CODE_FIXTURE = True\n'}
            def validation(mode, **kwargs):
                self.assertEqual(mode,'validate')
                context_path=m.BENCH/'validation-context.json'
                context=m.read_manifest(context_path if context_path.exists() else m.BENCH/m.MANIFEST_NAME)
                self.assertNotIn('archive',context,'Do not persist made-up archive hashes even in preliminary metadata')
                return {'status':'success','packages':{'torch':'2.8.0','torchvision':'0.23.0'}}
            m.run_subprocess=validation  # unavoidable GPU boundary; helpers/copy/archive remain REAL.
            report={'timings_seconds':{}}
            m.build_cache(report)
            self.assertEqual(len(calls),1)
            constraints,skip=calls[0]
            self.assertFalse(skip)
            self.assertEqual(constraints['nvidia-cublas-cu12'],'12.8')
            self.assertEqual(constraints['triton'],'3.4.0')
            archive=m.DRIVE/m.ARCHIVE_NAME
            manifest=m.read_manifest(m.DRIVE/m.MANIFEST_NAME)
            self.assertEqual(m.sha256_file(archive),manifest['archive']['sha256'])
            self.assertEqual(manifest['changed_distributions'],['newdependency'])
            self.assertEqual(report['changed_distribution_count'],1)
            self.assertTrue(report['drive_sha256_independent_readback_verified'])
            self.assertNotIn('benchmark_executed',report)  # This fixture is NOT a live benchmark.
            for phase in ['installation','validation','archive_build','drive_copy','drive_verification']:
                self.assertIn(phase,report['timings_seconds'])

    def test_child_audit_really_blocks_installer_before_spawn(self):
        m = load_runtime()
        self.assertTrue(callable(getattr(m,'run_child',None)), 'Fresh subprocess workflow missing')
        probe = '''import importlib.util,sys,subprocess\ns=importlib.util.spec_from_file_location('cache_runtime',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.install_child_audit_guard()\ntry: subprocess.run([sys.executable,'-m','pip','install','NO_NETWORK_FIXTURE'])\nexcept m.CacheAbort: print('INSTALL_BLOCKED_BEFORE_SPAWN')\nelse: raise AssertionError('Installer was allowed')'''
        result = subprocess.run([sys.executable,'-B','-c',probe,str(SCRIPT)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'INSTALL_BLOCKED_BEFORE_SPAWN')


class HardeningRegressionTests(unittest.TestCase):
    def test_preflight_prefix_is_not_a_license_to_run_arbitrary_python(self):
        m = load_runtime()
        attack = [sys.executable, '-c', 'import json, torch; import importlib.metadata as md; import os; os.system("pip install blocked")']
        with self.assertRaises(m.CacheAbort):
            m.check_child_command(attack)

    def test_framework_distinfo_names_cannot_be_smuggled_into_overlay(self):
        m = load_runtime()
        for name in ['packages/triton-3.4.0.dist-info/METADATA',
                     'packages/torchaudio-2.8.0.dist-info/RECORD',
                     'packages/nvidia_cublas_cu12-12.8.dist-info/METADATA',
                     'packages/torchgen/__init__.py', 'packages/functorch/__init__.py']:
            with self.subTest(name=name), self.assertRaises(m.CacheAbort):
                m.valid_member_name(name)

    def test_comfy_model_tree_and_package_git_metadata_are_not_archive_code(self):
        m=load_runtime()
        for name in ['code/ComfyUI/models/vae/weights.bin',
                     'code/ComfyUI/models/unet/weights.pth',
                     'packages/.git/config']:
            with self.subTest(name=name), self.assertRaises(m.CacheAbort):
                m.valid_member_name(name)
        m.valid_member_name('code/ComfyUI/models/vae/put_vaes_here')
        m.valid_member_name('code/ComfyUI/comfy/ldm/models/diffusion/model.py')

    def test_public_certifi_ca_and_long_native_package_paths_can_roundtrip(self):
        m = load_runtime()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root=Path(td)
            sources={'packages/certifi/cacert.pem':b'PUBLIC_ROOT_CA_FIXTURE',
                     'packages/demo/'+('a'*180)+'/'+('b'*180)+'.py':b'LONG_CODE_PATH_FIXTURE'}
            inventory=m.write_archive(root/'safe.tar.gz',sources)
            m.secure_extract(root/'safe.tar.gz',root/'safe',inventory)
            self.assertEqual((root/'safe'/'packages/certifi/cacert.pem').read_bytes(),b'PUBLIC_ROOT_CA_FIXTURE')
            with self.assertRaises(m.CacheAbort):
                m.valid_member_name('packages/secret.pem')

    def test_exact_original_probe_is_allowed_but_no_extended_probe_is_allowed(self):
        m=load_runtime()
        original=m.load_original(ROOT.parent/'colab-qwen-image-test'/'runtime_inference.py')
        probes=[v for v in original.preflight.__code__.co_consts if isinstance(v,str) and v.startswith('import json, torch; import importlib.metadata as md; ')]
        self.assertEqual(len(probes),1)
        m._ALLOWED_PREFLIGHT_PROBE=probes[0]
        m.check_child_command([sys.executable,'-c',probes[0]])
        with self.assertRaises(m.CacheAbort):
            m.check_child_command([sys.executable,'-c',probes[0]+'; print("extra")'])

    def test_tar_prefix_collisions_and_symlink_parent_are_rejected_before_write(self):
        m = load_runtime()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            root = Path(td)
            data = b'x'
            sources = {'packages/demo':data, 'packages/demo/child.py':data}
            archive = root/'collision.tar.gz'
            files = m.write_archive(archive, sources)
            target = root/'collision'
            with self.assertRaises(m.CacheAbort):
                m.secure_extract(archive,target,files)
            self.assertFalse(target.exists())
            archive = root/'good.tar.gz'
            files = m.write_archive(archive, {'packages/demo.py':data})
            outside = root/'outside'
            outside.mkdir()
            (root/'parent').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(m.CacheAbort):
                m.secure_extract(archive,root/'parent'/'dest',files)
            self.assertFalse((outside/'dest').exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
