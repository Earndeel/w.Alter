#!/opt/walter-colab/mcp/.venv/bin/python -B
"""One-shot notebook jobs; no purchases, credentials, keepalive or server.

--timeout-seconds bounds the Python subprocess, NOT allocation/transport time.
Cleanup is best-effort Python finally; a dead controller cannot guarantee deletion.
GPU launch is deliberately closed until a production preparation path is validated.
"""
import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

import transfer

ROOT = Path(__file__).resolve().parent
LOCK_DIR = ROOT / 'locks'
MAX_FILE = min(80 * 1024 * 1024, getattr(transfer, 'MAX_FILE', transfer.MAX_BYTES))


class GPUPreparationError(ValueError):
    """Authored local refusal, safe to report without external exception text."""


def require_gpu_preparation(device):
    """Temporary fail-closed interlock, NOT a model-readiness validator.

    No production bundle/restore path is validated yet. Included-units consent
    only grants a budget; it cannot certify dependencies, weights or workflows.
    Replace this interlock only alongside a real preparation validator and tests,
    not a ready=True flag, a CLI override or an empty readiness manifest.
    """
    if device != 'cpu':
        raise GPUPreparationError(
            'GPU preparation incomplete: validated dependencies, model assets and '
            'workflow restoration are required before allocation')


@dataclass(frozen=True)
class LocalFile:
    path: Path
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class JobSpec:
    script: LocalFile
    inputs: tuple[LocalFile, ...]
    outputs: tuple[str, ...]
    device: str
    timeout_seconds: int
    result_dir: Path
    allow_included_units: bool = False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    job = commands.add_parser('job')
    job.add_argument('script', type=Path)
    job.add_argument('--input', dest='inputs', type=Path, action='append', default=[])
    job.add_argument('--output', dest='outputs', action='append', default=[])
    job.add_argument('--device', choices=('cpu', 'T4', 'L4', 'A100'), default='cpu')
    job.add_argument('--allow-included-units', action='store_true')
    job.add_argument('--timeout-seconds', type=int, default=60)
    job.add_argument('--result-dir', type=Path, required=True)
    return parser.parse_args(argv)


def unlinked_path(path):
    path = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Symlink paths are refused')
    return path


def load_file(path, *, allow_empty=False):
    path = unlinked_path(path)
    name = transfer.safe_filename(path.name)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not int(not allow_empty) <= before.st_size <= MAX_FILE:
            raise ValueError('Script/input must be a regular file within the 80 MiB bound')
        digest, size = hashlib.sha256(), 0
        while True:
            chunk = handle.read(min(1024 * 1024, MAX_FILE + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE:
                raise ValueError('File grew beyond the 80 MiB bound')
            digest.update(chunk)
        after = os.fstat(handle.fileno())
        if size != before.st_size or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError('Local source changed while loading')
    return LocalFile(path, name, size, digest.hexdigest())


def prepare_job(args):
    # This gate precedes even local writes and construction of Browser.
    if args.device != 'cpu' and not args.allow_included_units:
        raise ValueError('GPU requires --allow-included-units; no new purchase is permitted')
    require_gpu_preparation(args.device)
    if not 1 <= args.timeout_seconds <= 3600:
        raise ValueError('timeout-seconds must be in 1..3600')
    script = load_file(args.script)
    inputs = tuple(load_file(path) for path in args.inputs)
    outputs = tuple(transfer.safe_filename(name) for name in args.outputs)
    names = [script.name, *(item.name for item in inputs), *outputs]
    if len(names) != len(set(names)):
        raise ValueError('Script/input/output names must not collide')
    result_dir = unlinked_path(args.result_dir)
    for name in outputs:
        target = result_dir / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError('Output collision is not a regular unlinked file')
    result_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(result_dir, 0o700, follow_symlinks=False)
    return JobSpec(script, inputs, outputs, args.device, args.timeout_seconds, result_dir, args.allow_included_units)


def job_code(spec):
    """Build a standalone cell; all interpolated values are validated literals."""
    transfer.safe_filename(spec.script.name)
    if spec.device not in ('cpu', 'T4', 'L4', 'A100') or not 1 <= spec.timeout_seconds <= 3600:
        raise ValueError('Invalid job command specification')
    return '''from pathlib import Path
import json, os, re, signal, subprocess, sys, tempfile, time
store = Path(''' + repr(transfer.STORE) + ''')
script_name = ''' + repr(spec.script.name) + '''
device = ''' + repr(spec.device) + '''
timeout_seconds = ''' + repr(spec.timeout_seconds) + '''
started = time.monotonic()
result = {'status': 'error', 'exitcode': None, 'stdout': '', 'stderr': '', 'gpu_names': None}
process = None
try:
    if store.is_symlink() or any(p.is_symlink() for p in store.parents) or not store.is_dir():
        raise ValueError('Unsafe runtime working directory')
    script = store / script_name
    if script.is_symlink() or not script.is_file():
        raise ValueError('Script must be an unlinked regular file')
    if device != 'cpu':
        check = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True, timeout=min(10, timeout_seconds))
        names = [name.strip() for name in check.stdout.splitlines() if name.strip()]
        pattern = r'(?<![A-Za-z0-9])' + re.escape(device) + r'(?![A-Za-z0-9])'
        if not names or not all(re.search(pattern, name) for name in names):
            raise ValueError('Requested GPU model was not allocated; no CPU fallback')
        result['gpu_names'] = names
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen([sys.executable, '-u', script_name], cwd=str(store),
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            process.wait(timeout=timeout_seconds)
            result['status'] = 'success' if process.returncode == 0 else 'error'
        except subprocess.TimeoutExpired:
            result['status'] = 'timeout'
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        finally:
            # Do not leave ordinary same-session descendants behind after a job.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        result['exitcode'] = process.returncode
        stdout.seek(0)
        stderr.seek(0)
        for key, stream in (('stdout', stdout), ('stderr', stderr)):
            text = stream.read(8192).decode('utf-8', errors='replace')
            result[key] = text.encode('utf-8')[:8192].decode('utf-8', errors='ignore')
except Exception as error:
    # Third-party errors may include secrets; only the class crosses the bridge.
    result['error_type'] = type(error).__name__
finally:
    result['cell_seconds'] = time.monotonic() - started
    print('WALTER_JOB_RESULT=' + json.dumps(result, ensure_ascii=False))
'''


def marker_json(text, prefix):
    import json
    values = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    if len(values) != 1:
        raise ValueError('Missing or ambiguous runtime result marker')
    value = json.loads(values[0])
    if not isinstance(value, dict):
        raise ValueError('Runtime result must be an object')
    return value


def parse_job_result(text):
    import math
    result = marker_json(text, 'WALTER_JOB_RESULT=')
    status = result.get('status')
    exitcode = result.get('exitcode')
    duration = result.get('cell_seconds')
    if (status not in ('success', 'timeout', 'error')
            or (exitcode is not None and type(exitcode) is not int)
            or (status == 'success' and exitcode != 0)
            or (status != 'success' and exitcode == 0)
            or type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0):
        raise ValueError('Invalid runtime job status or timing')
    if any(not isinstance(result.get(key), str) or len(result[key].encode('utf-8')) > 8192 for key in ('stdout', 'stderr')):
        raise ValueError('Invalid or unbounded runtime logs')
    return result


class OnDemandError(RuntimeError):
    """Safe public failure with a structured report, never raw third-party text."""
    def __init__(self, detail, report):
        super().__init__(detail)
        self.report = report


class CleanupError(OnDemandError):
    pass


def file_metadata_code(name, *, allow_missing=False):
    name = transfer.safe_filename(name)
    return '''from pathlib import Path
import hashlib, json, os, stat
store = Path(''' + repr(transfer.STORE) + ''')
name = ''' + repr(name) + '''
if store.is_symlink() or any(p.is_symlink() for p in store.parents) or not store.is_dir():
    raise ValueError('Unsafe runtime cache directory')
p = store / name
if p.is_symlink():
    raise ValueError('Runtime object is a symlink')
if not p.exists() and ''' + repr(allow_missing) + ''':
    result = {'name': name, 'exists': False}
else:
    with os.fdopen(os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= ''' + repr(MAX_FILE) + ''':
            raise ValueError('Runtime file outside bounded regular-file contract')
        h, size = hashlib.sha256(), 0
        while True:
            chunk = f.read(min(1048576, ''' + repr(MAX_FILE + 1) + ''' - size))
            if not chunk:
                break
            size += len(chunk)
            if size > ''' + repr(MAX_FILE) + ''':
                raise ValueError('Runtime file grew beyond bound')
            h.update(chunk)
        after = os.fstat(f.fileno())
        if size != before.st_size or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError('Runtime object changed during hashing')
    result = {'name': name, 'exists': True, 'size': size, 'sha256': h.hexdigest()}
print('WALTER_JOB_FILE=' + json.dumps(result))
'''


async def runtime_file_metadata(bridge, name, *, allow_missing=False):
    data = marker_json(await bridge.code(file_metadata_code(name, allow_missing=allow_missing)), 'WALTER_JOB_FILE=')
    if data.get('name') != name or type(data.get('exists')) is not bool:
        raise ValueError('Runtime metadata name/existence mismatch')
    if not data['exists']:
        if not allow_missing:
            raise ValueError('Requested output is absent')
        return data
    if (type(data.get('size')) is not int or not 0 <= data['size'] <= MAX_FILE
            or not isinstance(data.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', data['sha256'])):
        raise ValueError('Invalid bounded runtime metadata pin')
    return data


def matches_pin(item, pin):
    return item.size == pin['size'] and item.sha256 == pin['sha256']


async def upload_pinned(bridge, item):
    # Revalidate just before transfer; the original pre-allocation hash is immutable.
    current = await asyncio.to_thread(load_file, item.path)
    if current != item:
        raise ValueError('Local input changed since pre-allocation load')
    before = await runtime_file_metadata(bridge, item.name, allow_missing=True)
    if before['exists']:
        if not matches_pin(item, before):
            raise ValueError('Nonidentical runtime upload collision')
    else:
        await asyncio.to_thread(bridge.browser.upload, item.path)
    actual = await runtime_file_metadata(bridge, item.name)
    if not matches_pin(item, actual):
        raise ValueError('Uploaded runtime SHA256/size differs from loaded source')
    return actual


def check_local_collision(path, pin):
    path = unlinked_path(path)
    if not path.exists():
        return False
    actual = load_file(path, allow_empty=True)
    if not matches_pin(actual, pin):
        raise ValueError('Nonidentical local output collision; refusing overwrite')
    return True


async def download_pinned(bridge, name, result_dir):
    pin = await runtime_file_metadata(bridge, name)
    result_dir = unlinked_path(result_dir)
    target = result_dir / name
    if check_local_collision(target, pin):
        return {**pin, 'path': str(target), 'already_present': True}
    # Browser.download requires an absent target. Stage privately, then publish
    # with link (never rename-overwrite), so even a racing collision is refused.
    with tempfile.TemporaryDirectory(prefix='.walter-job-', dir=result_dir) as staging:
        staged = Path(staging) / name
        await asyncio.to_thread(bridge.browser.download, name, staged,
                                expected_sha256=pin['sha256'], expected_size_bytes=pin['size'])
        if not matches_pin(load_file(staged, allow_empty=True), pin):
            raise ValueError('Independent downloaded output SHA256/size mismatch')
        directory = os.open(unlinked_path(result_dir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                os.link(staged, name, dst_dir_fd=directory, follow_symlinks=False)
            except FileExistsError:
                if not check_local_collision(target, pin):
                    raise ValueError('Racing local output disappeared; result was not published')
        finally:
            os.close(directory)
    return {**pin, 'path': str(target), 'already_present': False}


def require_disconnected(state):
    if not isinstance(state, dict) or state.get('disconnected') is not True or state.get('connected', False) is not False:
        raise ValueError('Pre-existing or ambiguous runtime; no allocation or deletion allowed')


async def run_prepared(spec, bridge, *, clock=time.monotonic):
    """One attempt, cleanup inside the same MCP connection, minimal test doubles."""
    started = clock()
    report = {'status': 'error', 'device': spec.device, 'script': spec.script.name,
              'inputs': [], 'outputs': [], 'job': None, 'resources_before': None,
              'cleanup': {'attempted': False, 'disconnected': None, 'resources_after': None},
              'compute_units_consumed': None,
              'timings': {'total_seconds': None, 'cell_seconds': None}}
    ownership_attempted = False
    try:
        if spec.device != 'cpu' and not spec.allow_included_units:
            raise ValueError('GPU requires --allow-included-units')
        require_gpu_preparation(spec.device)
        command = job_code(spec)
        await asyncio.to_thread(bridge.browser.assert_target)
        async with bridge.connect():
            await asyncio.to_thread(bridge.browser.assert_target)
            require_disconnected(await asyncio.to_thread(bridge.runtime_state))
            selection = await asyncio.to_thread(bridge.ensure_runtime_kind, spec.device)
            if selection.get('selected') != spec.device or selection.get('disabled') is not False:
                raise ValueError('Requested device selection was not verified')
            report['resources_before'] = selection.get('resources_before')
            if report['resources_before'] is not None and report['resources_before'].get('active_sessions') != 0:
                raise ValueError('Pre-existing active Colab session; refusing allocation')
            require_disconnected(await asyncio.to_thread(bridge.runtime_state))
            try:
                ownership_attempted = True
                initialized = await bridge.initialize()
                if initialized.get('drive_mounted') or initialized.get('google_credentials_present'):
                    raise ValueError('Mount-free, credential-free runtime isolation failed')
                report['script_pin'] = await upload_pinned(bridge, spec.script)
                for item in spec.inputs:
                    report['inputs'].append(await upload_pinned(bridge, item))
                # Margin covers nvidia-smi and interpreter/cell bookkeeping. No
                # wait_for/retry around allocation or transfer, and no job rerun.
                job = parse_job_result(await bridge.code(command, timeout=spec.timeout_seconds + 45))
                report['job'] = job
                report['timings']['cell_seconds'] = job['cell_seconds']
                report['status'] = job['status']
                if job['status'] == 'success':
                    for name in spec.outputs:
                        report['outputs'].append(await download_pinned(bridge, name, spec.result_dir))
            finally:
                if ownership_attempted:
                    primary_error = sys.exc_info()[1]
                    if primary_error is not None:
                        report['primary_error_type'] = type(primary_error).__name__
                    report['cleanup']['attempted'] = True
                    try:
                        released = await asyncio.to_thread(bridge.delete_test_runtime)
                        report['cleanup'].update(released)
                        require_disconnected(released)
                        require_disconnected(await asyncio.to_thread(bridge.runtime_state))
                        resources = released.get('resources_after')
                        if resources is not None and resources.get('active_sessions') != 0:
                            raise ValueError('Cleanup left active Colab sessions')
                        report['cleanup'] = {**released, 'attempted': True}
                    except Exception as error:
                        report['status'] = 'error'
                        report['cleanup'].update(disconnected=False, error_type=type(error).__name__)
                        raise CleanupError('Runtime cleanup could not be verified', report) from None
    except OnDemandError:
        raise
    except Exception as error:
        report['status'] = 'error'
        report['error_type'] = type(error).__name__
        raise OnDemandError('Job failed; no reconnect, rerun or fallback attempted', report) from None
    finally:
        report['timings']['total_seconds'] = clock() - started
    return report


@contextmanager
def notebook_lock(notebook_id):
    """Serialize this CLI through cleanup; OS releases lock if controller dies."""
    if not isinstance(notebook_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', notebook_id):
        raise ValueError('Unsafe notebook lock identity')
    directory = unlinked_path(LOCK_DIR)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (notebook_id + '.lock')
    if path.is_symlink():
        raise ValueError('Symlink lock refused')
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as error:
        raise ValueError('Unsafe notebook lock') from error
    with os.fdopen(descriptor, 'r+b') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('Unsafe notebook lock')
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('A job for this notebook is already running') from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


async def execute(args, *, config=None, browser_factory=None, bridge_factory=None):
    started = time.monotonic()
    spec = prepare_job(args)
    if config is None:
        config = json.loads((ROOT / 'config.json').read_text())
    if config.get('new_purchase_allowed', False) or config.get('google_credentials_in_runtime_allowed', False):
        raise ValueError('Refusing widened purchase/credential policy')
    if bridge_factory is None:
        from bridge import Bridge
        bridge_factory = Bridge
    with notebook_lock(config['notebook_id']):
        browser = await asyncio.to_thread(browser_factory or transfer.Browser,
                                          config['browser_session'], config['notebook_id'])
        try:
            result = await run_prepared(spec, bridge_factory(browser))
        except OnDemandError as error:
            error.report['timings']['total_seconds'] = time.monotonic() - started
            raise
        result['timings']['total_seconds'] = time.monotonic() - started
        return result


def main(argv=None):
    args = parse_args(argv)
    started = time.monotonic()
    try:
        result = asyncio.run(execute(args))
    except GPUPreparationError as error:
        result = {'status': 'blocked', 'reason': 'gpu_preparation_incomplete',
                  'error_type': type(error).__name__, 'detail': str(error),
                  'allocation_requested': False,
                  'cleanup': {'attempted': False, 'disconnected': None},
                  'timings': {'total_seconds': time.monotonic() - started, 'cell_seconds': None},
                  'compute_units_consumed': None}
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1
    except OnDemandError as error:
        result = {**error.report, 'error_type': type(error).__name__, 'detail': str(error)}
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as error:
        # Never print raw external exceptions, config, signed URLs or credentials.
        result = {'status': 'error', 'error_type': type(error).__name__,
                  'detail': 'Invalid specification or unavailable bridge; no automatic retry or purchase.',
                  'cleanup': {'attempted': False, 'disconnected': None},
                  'timings': {'total_seconds': time.monotonic() - started, 'cell_seconds': None},
                  'compute_units_consumed': None}
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
