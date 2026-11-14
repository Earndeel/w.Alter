"""Offline transport regression tests: real files/cells, fake external boundaries.

Do not import the live test_bootstrap/test_*integration scripts in this suite.
"""
import asyncio
import base64
import hashlib
import io
import json
from contextlib import asynccontextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import drive_store
import run as runner
import transfer


class OfflineTests(unittest.TestCase):
    def setUp(self):
        # Any missed external boundary must fail instead of connecting anywhere.
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden in offline tests'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class StatusSafetyTests(OfflineTests):
    def test_status_reads_runtime_and_resources_without_initializing_or_allocating(self):
        config_root = self.root / 'config'
        config_root.mkdir()
        (config_root / 'config.json').write_text(json.dumps({
            'new_purchase_allowed': False, 'google_credentials_in_runtime_allowed': False,
            'drive_folder_id': 'offline-folder', 'browser_session': 'offline-session',
            'notebook_id': 'offline-notebook'}))
        calls = []
        runtime = {'disconnected': True}
        resources = {'active_sessions': 0}
        class BridgeFixture:
            def __init__(self, browser):
                pass

            @asynccontextmanager
            async def connect(self):
                calls.append('connect')
                yield self

            async def initialize(self):
                raise AssertionError('status must never initialize/allocate a runtime')

            def runtime_state(self):
                calls.append('runtime_state')
                return runtime

            def resources(self):
                calls.append('resources')
                return resources

        def forbid_drive(folder):
            raise AssertionError('status must not instantiate OAuth DriveStore')
        with patch.multiple(runner, ROOT=config_root, SCRATCH=self.root / 'scratch',
                            DriveStore=forbid_drive, Browser=lambda *args: object(),
                            Bridge=BridgeFixture):
            try:
                result = asyncio.run(runner.execute(SimpleNamespace(command='status')))
            except AssertionError as error:
                self.fail(str(error))
        self.assertEqual(result, {'runtime': runtime, 'resources': resources, 'allocation_requested': False})
        self.assertEqual(calls, ['runtime_state', 'resources'])
        self.assertFalse((self.root / 'scratch').exists())


class StageSafetyTests(OfflineTests):
    def stage_fixture(self, data=b'PINNED_CACHE'):
        store = self.root / 'runtime-store'
        store.mkdir()
        config_root = self.root / 'config'
        config_root.mkdir()
        (config_root / 'config.json').write_text(json.dumps({
            'new_purchase_allowed': False, 'google_credentials_in_runtime_allowed': False,
            'drive_folder_id': 'offline-folder', 'browser_session': 'offline-session',
            'notebook_id': 'offline-notebook'}))
        uploads = []
        downloads = []
        cells = []

        class StoreFixture:
            def __init__(self, folder):
                pass

            def fetch(self, name, destination):
                Path(destination).write_bytes(data)
                return {'name': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'size_bytes': len(data)}

            def save(self, path):
                return {'name': Path(path).name, 'sha256': transfer.sha256_file(path),
                        'size_bytes': Path(path).stat().st_size}

        class BrowserFixture:
            def __init__(self, session, notebook):
                pass

            def upload(self, path):
                uploads.append(Path(path).name)
                (store / Path(path).name).write_bytes(Path(path).read_bytes())
                return {'seconds': 0}

            def download(self, name, path, *, expected_sha256, expected_size_bytes=None):
                downloads.append({'sha256': expected_sha256, 'size_bytes': expected_size_bytes})
                Path(path).write_bytes((store / name).read_bytes())
                return {'sha256': transfer.sha256_file(path), 'size_bytes': Path(path).stat().st_size}

        class BridgeFixture:
            def __init__(self, browser):
                pass

            @asynccontextmanager
            async def connect(self):
                yield self

            async def initialize(self):
                return {'drive_mounted': False, 'google_credentials_present': False}

            async def code(self, code):
                cells.append(code)
                with redirect_stdout(io.StringIO()) as output:
                    exec(compile(code, '<offline-runtime-cell>', 'exec'), {})
                return output.getvalue()

        def execute(command='stage'):
            with patch.multiple(runner, ROOT=config_root, SCRATCH=self.root / 'scratch',
                                STORE=str(store), DriveStore=StoreFixture,
                                Browser=BrowserFixture, Bridge=BridgeFixture):
                return asyncio.run(runner.execute(SimpleNamespace(command=command, name='cache.bin')))

        execute.downloads = downloads
        return store, uploads, cells, execute

    def test_persist_pins_runtime_size_before_browser_download(self):
        store, uploads, cells, execute = self.stage_fixture()
        (store / 'cache.bin').write_bytes(b'PINNED_CACHE')
        result = execute('persist')
        self.assertEqual(execute.downloads, [{'sha256': hashlib.sha256(b'PINNED_CACHE').hexdigest(),
                                             'size_bytes': len(b'PINNED_CACHE')}])
        self.assertEqual(result['drive']['size_bytes'], len(b'PINNED_CACHE'))

    def test_stage_refuses_symlink_store_before_upload_or_skip(self):
        store, uploads, cells, execute = self.stage_fixture()
        actual = self.root / 'actual-store'
        store.rename(actual)
        (actual / 'cache.bin').write_bytes(b'PINNED_CACHE')
        store.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            execute()
        self.assertEqual(uploads, [])
        self.assertEqual((actual / 'cache.bin').read_bytes(), b'PINNED_CACHE')

    def test_stage_uploads_missing_object_only_after_runtime_inspection(self):
        store, uploads, cells, execute = self.stage_fixture()
        result = execute()
        self.assertEqual(uploads, ['cache.bin'])
        self.assertEqual((store / 'cache.bin').read_bytes(), b'PINNED_CACHE')
        self.assertEqual(len(cells), 2)
        self.assertFalse(result['upload_skipped'])

    def test_stage_refuses_symlink_object_even_with_identical_content(self):
        store, uploads, cells, execute = self.stage_fixture()
        actual = self.root / 'actual.bin'
        actual.write_bytes(b'PINNED_CACHE')
        (store / 'cache.bin').symlink_to(actual)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            execute()
        self.assertEqual(uploads, [])
        self.assertEqual(actual.read_bytes(), b'PINNED_CACHE')

    def test_stage_refuses_broken_symlink_object(self):
        store, uploads, cells, execute = self.stage_fixture()
        (store / 'cache.bin').symlink_to(self.root / 'absent.bin')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            execute()
        self.assertEqual(uploads, [])

    def test_runtime_inspection_refuses_symlink_store_parent(self):
        actual = self.root / 'actual-parent'
        (actual / 'store').mkdir(parents=True)
        parent = self.root / 'linked-parent'
        parent.symlink_to(actual, target_is_directory=True)
        with patch.object(runner, 'STORE', str(parent / 'store')):
            code = runner.runtime_hash_code('cache.bin', allow_missing=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            exec(compile(code, '<offline-runtime-cell>', 'exec'), {})

    def test_stage_skips_upload_when_runtime_content_is_identical(self):
        store, uploads, cells, execute = self.stage_fixture()
        target = store / 'cache.bin'
        target.write_bytes(b'PINNED_CACHE')
        inode = target.stat().st_ino
        result = execute()
        self.assertEqual(uploads, [], 'Identical content must not be uploaded again')
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual(result['runtime_readback']['sha256'], hashlib.sha256(b'PINNED_CACHE').hexdigest())
        self.assertTrue(result['upload_skipped'])

    def test_stage_refuses_different_runtime_content_before_upload(self):
        store, uploads, cells, execute = self.stage_fixture()
        target = store / 'cache.bin'
        target.write_bytes(b'EXISTING_DIFFERENT_CACHE')
        with self.assertRaisesRegex(ValueError, 'collision'):
            execute()
        self.assertEqual(target.read_bytes(), b'EXISTING_DIFFERENT_CACHE')
        self.assertEqual(uploads, [])
        self.assertTrue(cells, 'Runtime inspection must precede any upload')


class LocalFilesBrowser(transfer.Browser):
    """Execute production JavaScript in Node, never in a real browser/session."""
    def __init__(self, data=b'CACHE', navigate_on=None):
        self.notebook_id = 'offline-notebook'
        self.location = {'origin': 'https://colab.research.google.com', 'pathname': '/drive/offline-notebook'}
        self.state = None
        self.events = []
        self.data = data
        self.navigate_on = navigate_on

    def action(self, route, **args):
        if route != '/tab/evaluate':
            raise AssertionError('Unexpected external route in local JS fixture')
        expression = args['expression']
        if self.navigate_on and self.navigate_on in expression:
            self.location['pathname'] = '/drive/other-notebook'
        script = '''
const location=LOCATION;
const window={__walterXfer:STATE};
if(window.__walterXfer?.chunks)window.__walterXfer.chunks=window.__walterXfer.chunks.map(a=>Uint8Array.from(a));
if(window.__walterXfer?.blob)window.__walterXfer.blob=new Blob([Uint8Array.from(window.__walterXfer.blob)]);
let events=[];
class File extends Blob {constructor(parts,name,opts){super(parts,opts);this.name=name;}}
const colab={global:{notebook:{
  uploadFileToKernel:async()=>{events.push('upload')},
  getKernelFiles:()=>({download:async()=>{events.push('download');return new Blob([Buffer.from(DATA,'base64')])}})
}}};
(async()=>{
  let result,error;
  try {result=await eval(EXPRESSION)}catch(e){error=e.message}
  const s=window.__walterXfer;
  if(s?.chunks)s.chunks=s.chunks.map(a=>Array.from(a));
  if(s?.blob)s.blob=Array.from(new Uint8Array(await s.blob.arrayBuffer()));
  console.log(JSON.stringify({ok:!error,result:result??null,error,state:s??null,events}));
})()
'''
        for marker, value in [('LOCATION', self.location), ('STATE', self.state),
                              ('DATA', base64.b64encode(self.data).decode()), ('EXPRESSION', expression)]:
            script = script.replace(marker, json.dumps(value))
        response = json.loads(subprocess.check_output(['node', '-e', script], text=True))
        self.state = response['state']
        self.events.extend(response['events'])
        if not response['ok']:
            raise ValueError(response['error'])
        return response


class BrowserTargetSafetyTests(OfflineTests):
    def test_guarded_upload_still_sends_and_cleans_up_on_bound_notebook(self):
        browser = LocalFilesBrowser()
        source = self.root / 'cache.bin'
        source.write_bytes(b'CACHE')
        chunks = transfer.iter_chunks
        with patch.object(transfer, 'iter_chunks', lambda path: chunks(path, 2)):
            result = browser.upload(source)
        self.assertEqual(browser.events, ['upload'])
        self.assertIsNone(browser.state)
        self.assertEqual(result['source_sha256'], hashlib.sha256(b'CACHE').hexdigest())
        self.assertEqual(result['size_bytes'], len(b'CACHE'))

    def test_guarded_download_still_verifies_chunks_on_bound_notebook(self):
        browser = LocalFilesBrowser()
        target = self.root / 'cache.bin'
        with patch.object(transfer, 'CHUNK', 2):
            result = browser.download('cache.bin', target, expected_sha256=hashlib.sha256(browser.data).hexdigest(),
                                      expected_size_bytes=len(browser.data))
        self.assertEqual(target.read_bytes(), browser.data)
        self.assertEqual(browser.events, ['download'])
        self.assertIsNone(browser.state)
        self.assertTrue(result['independent_readback_verified'])
        self.assertFalse(target.with_name('cache.bin.part').exists())

    def test_download_hash_mismatch_removes_partial_file(self):
        browser = LocalFilesBrowser()
        target = self.root / 'cache.bin'
        with self.assertRaisesRegex(RuntimeError, 'SHA256'):
            browser.download('cache.bin', target, expected_sha256='0' * 64,
                             expected_size_bytes=len(browser.data))
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())
        self.assertIsNone(browser.state)

    def test_download_rejects_navigation_before_starting_transfer(self):
        browser = LocalFilesBrowser(navigate_on='f.download(')
        target = self.root / 'cache.bin'
        with self.assertRaisesRegex(ValueError, 'notebook'):
            browser.download('cache.bin', target, expected_sha256=hashlib.sha256(browser.data).hexdigest(),
                             expected_size_bytes=len(browser.data))
        self.assertEqual(browser.events, [])
        self.assertFalse(target.exists())

    def test_native_mutations_revalidate_notebook_before_browser_request(self):
        browser = transfer.Browser.__new__(transfer.Browser)
        browser.session, browser.tab = 'offline-session', 'offline-tab'
        def reject_target():
            raise ValueError('Bound notebook changed')
        browser.assert_target = reject_target
        for route, args in [('/tab/click-at', {'x': 1, 'y': 2}),
                            ('/tab/navigate', {'url': 'https://colab.research.google.com/drive/offline-notebook'})]:
            with self.subTest(route=route), patch.object(transfer.urllib.request, 'urlopen',
                    side_effect=lambda *a, **k: io.BytesIO(b'{"ok":true}')) as request:
                with self.assertRaisesRegex(ValueError, 'notebook'):
                    browser.action(route, **args)
                request.assert_not_called()

    def test_upload_revalidates_notebook_before_staging_each_chunk(self):
        browser = LocalFilesBrowser(navigate_on='s.chunks.push')
        source = self.root / 'cache.bin'
        source.write_bytes(b'CACHE')
        chunks = transfer.iter_chunks
        with patch.object(transfer, 'iter_chunks', lambda path: chunks(path, 2)), self.assertRaises(ValueError):
            browser.upload(source)
        self.assertEqual(browser.events, [], 'No upload may start on the wrong notebook')
        self.assertIsNotNone(browser.state, 'Cleanup must not mutate a different notebook')
        self.assertEqual(browser.state['received'], 0, 'The wrong notebook must not receive staged chunks')

    def test_download_revalidates_notebook_before_blob_read_and_cleanup(self):
        browser = LocalFilesBrowser(navigate_on='b.slice(')
        target = self.root / 'cache.bin'
        with patch.object(transfer, 'CHUNK', 2), self.assertRaises(ValueError):
            browser.download('cache.bin', target, expected_sha256=hashlib.sha256(browser.data).hexdigest(),
                             expected_size_bytes=len(browser.data))
        self.assertEqual(browser.events, ['download'])
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())
        self.assertIsNotNone(browser.state, 'Cleanup must not mutate the newly navigated notebook')


class BrowserSizeSafetyTests(OfflineTests):
    def test_download_rejects_blob_size_different_from_runtime_pin(self):
        data = b'CACHE'
        browser = transfer.Browser.__new__(transfer.Browser)
        reads = []
        browser.assert_target = lambda: None
        browser.wait_transfer = lambda: {'state': 'done', 'size': len(data)}
        def evaluate(expression):
            if 'b.slice(' in expression:
                reads.append(expression)
                return base64.b64encode(data).decode()
            return True
        browser.evaluate = evaluate
        target = self.root / 'cache.bin'
        with self.assertRaisesRegex(RuntimeError, 'size|byte'):
            browser.download('cache.bin', target, expected_sha256=hashlib.sha256(data).hexdigest(),
                             expected_size_bytes=len(data) - 1)
        self.assertEqual(reads, [], 'Do not extract any mismatching blob chunks')
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())

    def test_download_rejects_invalid_size_pins_without_browser_or_filesystem_actions(self):
        browser = transfer.Browser.__new__(transfer.Browser)
        browser.assert_target = lambda: self.fail('Contacted browser for invalid size')
        for size in [None, -1, transfer.MAX_BYTES + 1, True, False, '5', 5.0]:
            target = self.root / 'not-created' / 'cache.bin'
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'size'):
                browser.download('cache.bin', target, expected_sha256='0' * 64, expected_size_bytes=size)
            self.assertFalse(target.parent.exists())

    def test_download_requires_size_pin_before_any_browser_action(self):
        browser = transfer.Browser.__new__(transfer.Browser)
        calls = []
        browser.assert_target = lambda: calls.append('target')
        browser.evaluate = lambda expression: calls.append('evaluate') or False
        target = self.root / 'not-created' / 'cache.bin'
        with self.assertRaises(Exception) as rejection:
            browser.download('cache.bin', target, expected_sha256=hashlib.sha256(b'CACHE').hexdigest())
        self.assertEqual(calls, [], 'Missing size pin must fail before contacting the browser')
        self.assertIsInstance(rejection.exception, ValueError)
        self.assertIn('size', str(rejection.exception))
        self.assertFalse(target.parent.exists())


class DriveStreamSafetyTests(OfflineTests):
    def drive_fixture(self, expected, chunks):
        requests = []
        meta = {'id': 'offline-object', 'name': 'cache.bin', 'size': str(len(expected)),
                'trashed': False, 'permissions': [{'type': 'user', 'role': 'owner'}],
                'appProperties': {'walterSha256': hashlib.sha256(expected).hexdigest()},
                'md5Checksum': hashlib.md5(expected, usedforsecurity=False).hexdigest()}

        class OfflineHTTP:
            def request(self, uri, method, *, headers):
                index = len(requests)
                requests.append(dict(headers))
                chunk = chunks[index]
                start = sum(len(c) for c in chunks[:index])
                response = {'content-range': f'bytes {start}-{start + len(chunk) - 1}/{sum(map(len, chunks))}'}
                class Response(dict):
                    status = 206
                return Response(response), chunk

        class OfflineFiles:
            def get(self, **kwargs):
                return SimpleNamespace(execute=lambda: meta)

            def get_media(self, **kwargs):
                return SimpleNamespace(uri='https://offline.invalid/cache', http=OfflineHTTP(), headers={})

        store = drive_store.DriveStore.__new__(drive_store.DriveStore)
        store.find = lambda name: {'id': 'offline-object'}
        store.service = SimpleNamespace(files=lambda: OfflineFiles())
        return store, requests

    def test_fetch_accepts_exact_pinned_stream_and_verifies_checksums(self):
        store, requests = self.drive_fixture(b'ABC', [b'A', b'BC'])
        target = self.root / 'cache.bin'
        result = store.fetch('cache.bin', target)
        self.assertEqual(target.read_bytes(), b'ABC')
        self.assertEqual(len(requests), 2)
        self.assertEqual(result['sha256'], hashlib.sha256(b'ABC').hexdigest())
        self.assertTrue(result['independent_drive_readback_verified'])
        self.assertFalse(target.with_name('cache.bin.part').exists())

    def test_bounded_sink_refuses_excess_bytes_before_writing_them(self):
        handle = io.BytesIO()
        writer = drive_store._BoundedWriter(handle, 3)
        writer.write(b'AB')
        with self.assertRaisesRegex(RuntimeError, 'byte size'):
            writer.write(b'CD')
        self.assertEqual(handle.getvalue(), b'AB')
        writer.write(b'C')
        self.assertEqual(handle.getvalue(), b'ABC')

    def test_fetch_rejects_short_stream_and_removes_partial_file(self):
        store, requests = self.drive_fixture(b'ABC', [b'AB'])
        target = self.root / 'cache.bin'
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            store.fetch('cache.bin', target)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())

    def test_fetch_rejects_oversized_metadata_before_requesting_media(self):
        store, requests = self.drive_fixture(b'ABC', [b'ABC'])
        store.service.files().get().execute()['size'] = str(transfer.MAX_BYTES + 1)
        target = self.root / 'cache.bin'
        with self.assertRaisesRegex(ValueError, 'transfer limit'):
            store.fetch('cache.bin', target)
        self.assertEqual(requests, [])
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())

    def test_fetch_stops_stream_on_first_chunk_crossing_pinned_size(self):
        store, requests = self.drive_fixture(b'ABC', [b'AB', b'CD', b'EF'])
        target = self.root / 'cache.bin'
        with patch.object(drive_store, 'sha256_file', wraps=drive_store.sha256_file) as checksum:
            with self.assertRaises(RuntimeError):
                store.fetch('cache.bin', target)
            self.assertEqual(len(requests), 2, 'Do not fetch further chunks after crossing the runtime bound')
            checksum.assert_not_called()
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name('cache.bin.part').exists())


if __name__ == '__main__':
    unittest.main()
