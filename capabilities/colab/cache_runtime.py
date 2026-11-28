#!/usr/bin/env python3
"""Prepared dependency archive benchmark, restricted to interactive Google Colab.

Usage: !python /content/cache_runtime.py build
       !python /content/cache_runtime.py restore   # a genuinely NEW runtime
The parent injects the unchanged /content/walter-qwen-inference.py. By default,
Drive must already be mounted at /content/drive with its private cache directory.
Set WALTER_COLAB_CACHE_DIR=/content/walter-cache-store to use an existing regular
local staging directory instead; the parent handles transport with credentials
kept off the runtime. Local staging is ephemeral, not verified Drive persistence.
Import is offline/CPU safe. This module does not allocate runtimes, mount Drive,
or import Google authentication.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import importlib.metadata as metadata
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import site
import struct
import subprocess
import sys
import sysconfig
import tarfile
import time
import zlib

CONTENT = Path('/content')
BENCH = CONTENT / 'walter-cache-benchmark'
DRIVE_MOUNT = CONTENT / 'drive'
DRIVE = DRIVE_MOUNT / 'MyDrive' / 'W.Alter Colab Cache'
ORIGINAL = CONTENT / 'walter-qwen-inference.py'
ORIGINAL_SHA256 = '28f153ef9ffd9b61a3e0049fc15f112054d2b405891a5513ebf4dacb2b1d278b'
COMFY = CONTENT / 'walter-qwen-image-test' / 'ComfyUI'
GGUF = COMFY / 'custom_nodes' / 'ComfyUI-GGUF'
OVERLAY = BENCH / 'packages'
ARCHIVE_NAME = 'walter-comfy-dependencies-v1.tar.gz'
MANIFEST_NAME = 'walter-comfy-dependencies-v1.json'
BUILD_JSON = CONTENT / 'walter-cache-build.json'
RESTORE_JSON = CONTENT / 'walter-cache-restore.json'
SCHEMA = 1
MAX_MEMBERS = 100000
MAX_ARCHIVE_BYTES = 12 * 2**30
_ALLOWED_PREFLIGHT_PROBE: str | None = None


class CacheAbort(RuntimeError):
    """Authored, safe-to-report error; never include third-party secret payloads."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def protected(name: str) -> bool:
    name = canonical(name)
    return name in {'torch', 'torchvision', 'torchaudio', 'triton', 'pytorch-triton', 'nvidia'} or name.startswith('nvidia-')


def valid_member_name(name: str) -> None:
    parts = name.split('/')
    if (not name or '\\' in name or '\x00' in name or len(name) > 4096
            or any(p in {'', '.', '..'} for p in parts)
            or any(':' in p for p in parts)):
        raise CacheAbort('Unsafe archive path')
    if parts[0] == 'packages' and len(parts) >= 2:
        namespace = re.split(r'[-_]\d', parts[1].split('.dist-info')[0])[0]
        if protected(namespace) or namespace in {'torchgen', 'functorch'}:
            raise CacheAbort('Framework files must never enter the overlay')
    elif parts[:2] != ['code', 'ComfyUI'] or len(parts) < 3:
        raise CacheAbort('Archive content outside code and dependency allowlist')
    lower = [p.lower() for p in parts]
    if any(p in {'__pycache__', '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache',
                 '.huggingface', '.ssh', 'secrets', '.secrets'} for p in lower):
        raise CacheAbort('Caches or secret directories forbidden in archive')
    leaf = lower[-1]
    if (leaf.endswith(('.pyc', '.pyo', '.gguf', '.safetensors', '.ckpt', '.pth.tar', '.pt', '.onnx', '.key'))
            or (leaf.endswith('.pem') and name != 'packages/certifi/cacert.pem')
            or leaf in {'.env', '.netrc', '.git-credentials', 'token', 'credentials.json', 'secrets.json'}
            or leaf.startswith('.env.')):
        raise CacheAbort('Weights, bytecode or credentials forbidden in archive')
    if parts[:3] == ['code', 'ComfyUI', 'models'] and not (leaf.endswith(('.md', '.txt')) or leaf == '.gitkeep' or re.fullmatch(r'put_[a-z0-9_]+_here', leaf)):
        raise CacheAbort('ComfyUI models tree may contain only tracked documentation/empty placeholders')
    if '.git' in parts:
        index = parts.index('.git')
        if parts[:index] not in [['code', 'ComfyUI'], ['code', 'ComfyUI', 'custom_nodes', 'ComfyUI-GGUF']]:
            raise CacheAbort('Git metadata is permitted only for the two code checkouts')
        suffix = '/'.join(parts[index + 1:])
        if suffix not in {'HEAD', 'config', 'index', 'shallow', 'refs/heads/walter-cache'} and not re.fullmatch(
                r'objects/(?:[0-9a-f]{2}/[0-9a-f]{38}|pack/pack-[0-9a-f]{40}\.(?:pack|idx|rev))', suffix):
            raise CacheAbort('Only minimal sanitized git metadata is permitted')


def secure_extract(archive: Path, destination: Path, files: dict) -> None:
    """Validate the ENTIRE tar before creating anything; regular files only."""
    if destination.exists() or destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
        raise CacheAbort('Extraction target and its parents must be unlinked and target absent')
    if not hasattr(tarfile, 'data_filter'):
        raise CacheAbort('Python tarfile data filter unavailable; no unsafe fallback')
    if not isinstance(files, dict) or len(files) > MAX_MEMBERS:
        raise CacheAbort('Invalid archive inventory')
    for name, spec in files.items():
        valid_member_name(name)
        if (not isinstance(spec, dict) or not isinstance(spec.get('size_bytes'), int)
                or spec['size_bytes'] < 0 or not re.fullmatch(r'[0-9a-f]{64}', str(spec.get('sha256', '')))):
            raise CacheAbort('Invalid file inventory entry')
    for name in files:
        if any(parent.as_posix() in files for parent in PurePosixPath(name).parents):
            raise CacheAbort('Archive file/directory prefix collision')
    if sum(spec['size_bytes'] for spec in files.values()) > MAX_ARCHIVE_BYTES:
        raise CacheAbort('Archive unpacked size exceeds conservative limit')
    try:
        with tarfile.open(archive, 'r:gz') as handle:
            members = []
            seen = set()
            for member in handle:
                valid_member_name(member.name)
                if (not member.isreg() or member.issparse() or member.name in seen
                        or member.name not in files or member.size != files[member.name]['size_bytes']
                        or member.mode & 0o7000 or member.pax_headers):
                    raise CacheAbort('Unsafe, duplicate or unexpected tar content')
                seen.add(member.name)
                members.append(member)
                if len(members) > MAX_MEMBERS:
                    raise CacheAbort('Too many archive entries')
                stream = handle.extractfile(member)
                digest = hashlib.sha256()
                with stream:
                    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                        digest.update(block)
                if digest.hexdigest() != files[member.name]['sha256']:
                    raise CacheAbort('Archived file hash mismatch')
            if seen != set(files):
                raise CacheAbort('Archive inventory has missing entries')
            destination.mkdir(parents=True)
            handle.extractall(destination, members=members, filter='data')
        for name, spec in files.items():
            target = destination / name
            if target.is_symlink() or target.stat().st_size != spec['size_bytes'] or sha256_file(target) != spec['sha256']:
                raise CacheAbort('Extracted file verification failed')
    except (tarfile.TarError, OSError, EOFError) as error:
        raise CacheAbort('Archive decoding or extraction failed') from error


def site_roots() -> list[Path]:
    roots = {*site.getsitepackages(), sysconfig.get_path('purelib'), sysconfig.get_path('platlib')}
    return sorted({Path(p).resolve() for p in roots if p and Path(p).is_dir()})


def snapshot_distributions(roots: list[Path] | None = None) -> dict:
    roots = [p.resolve() for p in (site_roots() if roots is None else roots)]
    snapshot = {}
    for dist in metadata.distributions(path=[str(p) for p in roots]):
        name = canonical(dist.metadata['Name'])
        info = Path(dist._path).resolve()  # PathDistribution; actual .dist-info, not sys.path guesses.
        matches = [root for root in roots if info.is_relative_to(root)]
        if not matches or name in snapshot:
            raise CacheAbort('Distribution has duplicate metadata or lives outside site-packages')
        root = max(matches, key=lambda p: len(p.parts))
        record = info / 'RECORD'
        raw = record.read_bytes() if record.is_file() else None
        snapshot[name] = {'name': dist.metadata['Name'], 'version': dist.version,
                          'site_root': str(root), 'metadata_dir': str(info.relative_to(root)),
                          'record_sha256': hashlib.sha256(raw).hexdigest() if raw is not None else None,
                          'record_entries': [row[0] for row in csv.reader(io.StringIO(raw.decode('utf-8')))
                                             if row] if raw is not None else []}
    return snapshot


def changed_distributions(before: dict, after: dict) -> list[str]:
    if set(before) - set(after):
        raise CacheAbort('Setup removed a distribution; an additive overlay cannot reproduce removal')
    changed = [name for name, value in after.items() if name not in before or
               (value['version'], value['record_sha256']) != (before[name]['version'], before[name]['record_sha256'])]
    if any(protected(name) for name in changed):
        raise CacheAbort('Setup changed supplied torch/torchvision/triton/nvidia distribution; archive aborted')
    return sorted(changed)


def package_sources(changed: list[str], snapshot: dict) -> tuple[dict, list, dict]:
    sources = {}
    packages = []
    skipped = {'outside_site_packages': 0, 'bytecode_or_cache': 0}
    for name in changed:
        if protected(name):
            raise CacheAbort('Protected framework distribution cannot be archived')
        value = snapshot[name]
        if not value['record_sha256'] or not value['metadata_dir'].endswith('.dist-info'):
            raise CacheAbort('Changed package lacks wheel RECORD/.dist-info provenance')
        root = Path(value['site_root']).resolve()
        archived = []
        for entry in value['record_entries']:
            if '\\' in entry or '\x00' in entry or PurePosixPath(entry).is_absolute():
                raise CacheAbort('Invalid distribution RECORD path')
            lexical = Path(os.path.abspath(root / entry))
            if not lexical.is_relative_to(root):
                skipped['outside_site_packages'] += 1  # console scripts ../bin deliberately excluded.
                continue
            rel = lexical.relative_to(root).as_posix()
            if rel.endswith(('.pyc', '.pyo')) or any(p in {'__pycache__', '.cache'} for p in lexical.parts):
                skipped['bytecode_or_cache'] += 1
                continue
            if lexical.is_symlink() or not lexical.resolve().is_relative_to(root) or not lexical.is_file():
                raise CacheAbort('Package file is missing, a symlink, or resolves outside site-packages')
            path = lexical.resolve()
            archive_name = 'packages/' + rel
            valid_member_name(archive_name)
            if archive_name in sources and sources[archive_name] != path:
                raise CacheAbort('Different site-packages roots collide in the flat overlay')
            sources[archive_name] = path
            archived.append(archive_name)
        record_name = 'packages/' + value['metadata_dir'] + '/RECORD'
        metadata_name = 'packages/' + value['metadata_dir'] + '/METADATA'
        if record_name not in archived or metadata_name not in archived:
            raise CacheAbort('Overlay does not include distribution RECORD and METADATA')
        packages.append({k: value[k] for k in ['name', 'version', 'site_root', 'metadata_dir', 'record_sha256']})
        packages[-1].update({'canonical_name': name, 'overlay_metadata_dir': value['metadata_dir'],
                             'archived_file_count': len(set(archived))})
    return sources, packages, skipped


def write_archive(path: Path, sources: dict) -> dict:
    if path.exists() or path.is_symlink() or len(sources) > MAX_MEMBERS:
        raise CacheAbort('Archive target already exists or too many members')
    inventory = {}
    total = 0
    with tarfile.open(path, 'w:gz', compresslevel=1, format=tarfile.GNU_FORMAT) as handle:
        for name, source in sorted(sources.items()):
            valid_member_name(name)
            if isinstance(source, bytes):
                data = source
                entry = tarfile.TarInfo(name)
                entry.mode = 0o644
                entry.size = len(data)
                stream = io.BytesIO(data)
                digest = hashlib.sha256(data).hexdigest()
            else:
                if source.is_symlink() or not source.is_file():
                    raise CacheAbort('Archive source must be a regular file')
                entry = handle.gettarinfo(str(source), arcname=name)
                entry.mode &= 0o755
                stream = source.open('rb')
                digest = sha256_file(source)
            total += entry.size
            if total > MAX_ARCHIVE_BYTES:
                stream.close()
                raise CacheAbort('Archive source exceeds size limit')
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = ''
            entry.mtime = 0
            with stream:
                handle.addfile(entry, stream)
            inventory[name] = {'size_bytes': entry.size, 'sha256': digest}
    return inventory


def copy_and_verify(source: Path, destination: Path, expected_sha256: str) -> tuple[float, float]:
    if destination.exists() or destination.is_symlink():
        raise CacheAbort('Copy destination already exists; never overwrite an existing cache')
    temporary = destination.with_suffix(destination.suffix + '.partial')
    if temporary.exists() or temporary.is_symlink():
        raise CacheAbort('Incomplete copy target already exists')
    started = time.perf_counter()
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    copied = time.perf_counter() - started
    started = time.perf_counter()
    if sha256_file(destination) != expected_sha256:
        raise CacheAbort('Independent SHA256 readback differs after archive copy')
    return round(copied, 4), round(time.perf_counter() - started, 4)


def git_output(path: Path, args: list[str]) -> str:
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_CONFIG_SYSTEM': '/dev/null'}
    result = subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.askPass=',
                             '-c', 'http.extraHeader=', *args], cwd=path, env=env,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise CacheAbort('Local git verification failed; no network recovery attempted')
    return result.stdout


def repository_sources(path: Path, prefix: str, revision: str, url: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', revision) or not re.fullmatch(r'https://[^\s"\\]+', url):
        raise CacheAbort('Invalid pinned repository identity')
    path = path.resolve()
    if (not (path / '.git').is_dir() or (path / '.git').is_symlink()
            or (path / '.git' / 'commondir').exists() or (path / '.git' / 'objects' / 'info' / 'alternates').exists()):
        raise CacheAbort('Code cache requires a standalone checkout without external object storage')
    if (git_output(path, ['rev-parse', 'HEAD']).strip() != revision
            or git_output(path, ['remote', 'get-url', 'origin']).strip() != url
            or git_output(path, ['status', '--porcelain', '--untracked-files=no']).strip()):
        raise CacheAbort('Code checkout is not clean at the pinned revision/origin')
    sources = {}
    for entry in git_output(path, ['ls-files', '--stage', '-z']).split('\x00'):
        if not entry:
            continue
        mode_object_stage, relative = entry.split('\t', 1)
        mode, _, stage = mode_object_stage.split()
        if mode not in {'100644', '100755'} or stage != '0':
            raise CacheAbort('Archive forbids git symlinks, submodules or conflicted paths')
        name = prefix + '/' + relative
        valid_member_name(name)
        source = path / relative
        if source.is_symlink() or not source.resolve().is_relative_to(path) or not source.is_file():
            raise CacheAbort('Code source missing or escaping checkout')
        sources[name] = source.resolve()
    # Only essential object storage and index, NOT original config, hooks, refs or logs.
    for source in (path / '.git' / 'objects').rglob('*'):
        if source.is_symlink():
            raise CacheAbort('Git object storage contains a symlink')
        if source.is_file():
            relative = source.relative_to(path).as_posix()
            if '/objects/info/' in relative:
                continue  # commit graphs/packs lookup accelerators are not needed.
            name = prefix + '/' + relative
            valid_member_name(name)
            sources[name] = source
    index = path / '.git' / 'index'
    if not index.is_file() or index.is_symlink():
        raise CacheAbort('Clean code checkout lacks a regular git index')
    sources[prefix + '/.git/index'] = index
    shallow = path / '.git' / 'shallow'
    if shallow.exists():
        raw = shallow.read_bytes()
        if not raw or not all(re.fullmatch(rb'[0-9a-f]{40}', line) for line in raw.splitlines()):
            raise CacheAbort('Invalid shallow git boundary')
        sources[prefix + '/.git/shallow'] = raw
    sources[prefix + '/.git/HEAD'] = (revision + '\n').encode('ascii')
    # Git discovery requires a refs directory; reconstruct one sanitized ref.
    sources[prefix + '/.git/refs/heads/walter-cache'] = (revision + '\n').encode('ascii')
    sources[prefix + '/.git/config'] = (
        '[core]\n\trepositoryformatversion = 0\n\tbare = false\n\tfilemode = true\n'
        '\tlogallrefupdates = false\n[remote "origin"]\n\turl = ' + url + '\n').encode('utf-8')
    return sources


def activate_overlay(overlay: Path) -> None:
    root = str(overlay.resolve())
    if not overlay.is_dir() or overlay.is_symlink():
        raise CacheAbort('Missing regular dependency overlay')
    site.addsitedir(root)  # Required: PYTHONPATH alone does NOT process .pth.
    sys.path[:] = [root, *[p for p in sys.path if p != root]]
    # Propagate .pth-added directory paths to original's fresh torch preflight.
    os.environ['PYTHONPATH'] = os.pathsep.join(p for p in sys.path if p and Path(p).is_absolute())


def verify_overlay(packages: list[dict], overlay: Path) -> dict:
    verified = {}
    root = overlay.resolve()
    for item in packages:
        if protected(item['name']):
            raise CacheAbort('Manifest illegally overlays a protected framework')
        try:
            dist = metadata.distribution(item['name'])
        except metadata.PackageNotFoundError as error:
            raise CacheAbort('Restored distribution cannot be resolved') from error
        expected = root / item['overlay_metadata_dir']
        if (not expected.resolve().is_relative_to(root) or Path(dist._path).resolve() != expected.resolve()
                or dist.version != item['version'] or sha256_file(expected / 'RECORD') != item['record_sha256']):
            raise CacheAbort('Restored distribution version/RECORD/provenance mismatch')
        verified[canonical(item['name'])] = {'version': dist.version, 'metadata_path': str(expected),
                                          'record_sha256': item['record_sha256']}
    return verified


def load_original(path: Path = ORIGINAL):
    if not path.is_file() or path.is_symlink() or sha256_file(path) != ORIGINAL_SHA256:
        raise CacheAbort('Original inference script bytes differ from the inspected immutable script')
    spec = importlib.util.spec_from_file_location('walter_original_inference', path)
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    return original


def call_original_no_install(original) -> int:
    original_setup = original.setup_dependencies
    def cached_setup(framework, *, skip_setup):
        return original_setup(framework, skip_setup=True)
    # ONLY this monkeypatch. In particular main([]), NOT --skip-setup: model
    # downloads plus pinned template fetch/hash remain authorized and unchanged.
    original.setup_dependencies = cached_setup
    return original.main([])


def verify_png(path: Path, width: int, height: int, evidence: dict) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 128 * 2**20:
        raise CacheAbort('Missing, linked or oversized PNG')
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise CacheAbort('Output is not a PNG')
    offset = 8
    first = True
    finished = False
    compressed = bytearray()
    channels = None
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise CacheAbort('Truncated PNG chunk')
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(raw):
            raise CacheAbort('PNG chunk size exceeds file')
        data = raw[offset + 8:end - 4]
        crc = struct.unpack('>I', raw[end - 4:end])[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc:
            raise CacheAbort('PNG CRC verification failed')
        if first:
            if kind != b'IHDR' or size != 13:
                raise CacheAbort('PNG lacks initial IHDR')
            w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if (w, h) != (width, height) or depth != 8 or color not in {2, 6} or any([compression, filtering, interlace]):
                raise CacheAbort('PNG geometry/encoding differs from one requested RGB/RGBA image')
            channels = 3 if color == 2 else 4
            first = False
        elif kind == b'IHDR':
            raise CacheAbort('Duplicate PNG IHDR')
        if kind == b'IDAT':
            compressed.extend(data)
        if kind == b'IEND':
            if size or end != len(raw):
                raise CacheAbort('Invalid PNG IEND/trailing content')
            finished = True
        offset = end
    if not finished or not channels or not compressed:
        raise CacheAbort('Incomplete PNG')
    expected_bytes = height * (width * channels + 1)
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), expected_bytes + 1)
    except zlib.error as error:
        raise CacheAbort('Invalid PNG compressed pixel stream') from error
    if (len(pixels) != expected_bytes or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or any(pixels[row * (width * channels + 1)] > 4 for row in range(height))):
        raise CacheAbort('PNG pixel stream is invalid or exceeds its geometry')
    verified = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw),
                'width': width, 'height': height, 'mode': 'RGB' if channels == 3 else 'RGBA', 'image_count': 1}
    for key in ['sha256', 'size_bytes', 'width', 'height', 'image_count']:
        if evidence.get(key) != verified[key]:
            raise CacheAbort('PNG disagrees with original inference evidence: ' + key)
    return verified


def verify_inference_evidence(result: dict, request: dict, model_dir: Path, png: Path) -> dict:
    if result.get('status') != 'success' or result.get('runtime_script_sha256') != ORIGINAL_SHA256:
        raise CacheAbort('Original inference did not report success with the pinned script')
    if result.get('model_revision') != request['model_revision']:
        raise CacheAbort('Original result model revision differs')
    verified = result.get('model_files_verified', [])
    if len(verified) != len(request['model_files']):
        raise CacheAbort('Missing model verification evidence')
    for expected, actual in zip(request['model_files'], verified):
        path = model_dir / expected['local_path']
        if (actual.get('repo_path') != expected['repo_path'] or actual.get('revision') != request['model_revision']
                or actual.get('sha256') != expected['sha256'] or actual.get('size_bytes') != expected['size']
                or actual.get('path') != str(path) or not path.is_file() or path.stat().st_size != expected['size']):
            raise CacheAbort('Pinned model hash/size/revision verification evidence differs')
    # The unchanged original performed real SHA256 of ALL weights before
    # inference. Do not rehash ~14GB a second time and call it restore overhead.
    if result.get('output', {}).get('path') != str(png):
        raise CacheAbort('Original returned a different image path')
    return verify_png(png, request['parameters']['width'], request['parameters']['height'], result['output'])


def require_colab() -> None:
    try:
        found = importlib.util.find_spec('google.colab') is not None
    except (ImportError, ValueError):
        found = False
    if not found or not CONTENT.is_dir() or platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise CacheAbort('Restricted to an interactive Linux x86_64 Google Colab runtime; no VM installation or GPU access')


def require_drive() -> None:
    candidates = [DRIVE_MOUNT, DRIVE_MOUNT / 'MyDrive']
    if not any(p.is_mount() for p in candidates) or not DRIVE.is_dir() or DRIVE.is_symlink():
        raise CacheAbort('Google Drive must already be mounted and the private cache directory must exist')


def require_store() -> Path:
    """Validate explicit local staging or retain the unchanged mounted-Drive guard.

    Validate the literal opt-in before constructing a Path; never normalize,
    create, mount, or authorize a store on behalf of the caller.
    """
    value = os.environ.get('WALTER_COLAB_CACHE_DIR')
    if value is None:
        require_drive()
        return DRIVE
    if value != '/content/walter-cache-store':
        raise CacheAbort('WALTER_COLAB_CACHE_DIR must be exactly /content/walter-cache-store')
    store = Path(value)
    if store.is_symlink() or any(parent.is_symlink() for parent in store.parents):
        raise CacheAbort('Local staging cache directory and its parents must not be symlinks')
    if not store.is_dir():
        raise CacheAbort('Local staging cache directory must already exist')
    return store


def check_compatibility(expected: dict, actual: dict, changed: list[str]) -> None:
    required = ['machine', 'system', 'python_abi', 'python_major_minor', 'torch', 'torchvision', 'cuda']
    for key in required:
        if not expected.get(key) or expected[key] != actual.get(key):
            raise CacheAbort('Incompatible Colab base: ' + key + '; rebuild in the new base, no pip fallback')
    if 'numpy' not in {canonical(n) for n in changed} and expected.get('numpy') != actual.get('numpy'):
        raise CacheAbort('Incompatible base numpy not replaced by overlay')


def check_child_command(argv) -> None:
    """Audit allowlist: no pip, shells, git fetch/clone, or other installers."""
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
        raise CacheAbort('Restore forbids shell or ambiguous subprocess execution')
    program = Path(argv[0]).name
    args = list(argv[1:])
    if program == 'git':
        while args[:1] == ['-c']:
            if len(args) < 2 or args[1] not in {'credential.helper=', 'core.askPass=', 'http.extraHeader='}:
                raise CacheAbort('Unexpected git subprocess configuration')
            args = args[2:]
        if args in [['rev-parse', 'HEAD'], ['remote', 'get-url', 'origin'],
                    ['status', '--porcelain', '--untracked-files=no']]:
            return
    elif program == 'nvidia-smi' and args == [
            '--query-gpu=name,uuid,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits']:
        return
    elif Path(argv[0]).resolve() == Path(sys.executable).resolve() and len(args) == 2 and args[0] == '-c':
        if _ALLOWED_PREFLIGHT_PROBE is not None and args[1] == _ALLOWED_PREFLIGHT_PROBE:
            return  # Exact pinned original preflight is the sole caller.
    raise CacheAbort('Restore blocked a non-allowlisted process; no dependency installation is permitted')


def install_child_audit_guard(original=None) -> None:
    global _ALLOWED_PREFLIGHT_PROBE
    if original is not None:
        candidates = [v for v in original.preflight.__code__.co_consts if isinstance(v, str)
                      and v.startswith('import json, torch; import importlib.metadata as md; ')]
        if len(candidates) != 1:
            raise CacheAbort('Cannot identify the exact pinned preflight subprocess')
        _ALLOWED_PREFLIGHT_PROBE = candidates[0]
    def audit(event, args):
        if event == 'subprocess.Popen':
            check_child_command(args[1])
        elif event in {'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn'}:
            raise CacheAbort('Restore blocked shell or direct process execution')
    sys.addaudithook(audit)


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def print_summary(mode: str, report: dict, path: Path) -> None:
    summary = {key: report[key] for key in ['status', 'stage', 'timings_seconds', 'error',
               'storage_mode', 'cache_store_path', 'archive', 'output', 'changed_distribution_count'] if key in report}
    summary['result_json'] = str(path)
    raw = json.dumps(summary, ensure_ascii=False, separators=(',', ':'))
    if len(raw.encode('utf-8')) > 12000:
        raw = json.dumps({'status': report['status'], 'result_json': str(path), 'details_in_json': True})
    print('WALTER_CACHE_' + mode.upper() + '_JSON=' + raw, flush=True)


@contextmanager
def measured(report: dict, name: str):
    report['stage'] = name
    started = time.perf_counter()
    try:
        yield
    finally:
        report['timings_seconds'][name] = round(time.perf_counter() - started, 4)


def read_manifest(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 100 * 2**20:
        raise CacheAbort('Missing, linked or oversized dependency cache manifest')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as error:
        raise CacheAbort('Cache manifest cannot be decoded') from error
    if not isinstance(value, dict):
        raise CacheAbort('Manifest must be a JSON object')
    return value


def validate_context(manifest: dict, original) -> None:
    request = original.request_manifest()
    if (manifest.get('schema') != SCHEMA or manifest.get('original_script_sha256') != ORIGINAL_SHA256
            or manifest.get('cache_script_sha256') != sha256_file(Path(__file__).resolve())
            or manifest.get('request') != request or manifest.get('code_revisions') != request['code_revisions']):
        raise CacheAbort('Cache manifest source, settings or code revisions differ from pinned original')


def validate_manifest(manifest: dict, original) -> None:
    validate_context(manifest, original)
    archive = manifest.get('archive', {})
    if (archive.get('filename') != ARCHIVE_NAME or archive.get('compression_level') != 1
            or not re.fullmatch(r'[0-9a-f]{64}', str(archive.get('sha256', '')))
            or not isinstance(archive.get('size_bytes'), int) or not 0 < archive['size_bytes'] <= MAX_ARCHIVE_BYTES):
        raise CacheAbort('Invalid cache archive identity')
    if not isinstance(manifest.get('files'), dict) or len(manifest['files']) > MAX_MEMBERS:
        raise CacheAbort('Invalid archive inventory in manifest')
    for name, spec in manifest['files'].items():
        valid_member_name(name)
        if (not isinstance(spec, dict) or not isinstance(spec.get('size_bytes'), int) or spec['size_bytes'] < 0
                or not re.fullmatch(r'[0-9a-f]{64}', str(spec.get('sha256', '')))):
            raise CacheAbort('Invalid manifest file size/hash')
    if (archive.get('file_count', len(manifest['files'])) != len(manifest['files'])
            or archive.get('unpacked_size_bytes', sum(s['size_bytes'] for s in manifest['files'].values()))
               != sum(s['size_bytes'] for s in manifest['files'].values())):
        raise CacheAbort('Declared archive totals differ from its inventory')
    packages = manifest.get('packages')
    if not isinstance(packages, list) or any(not isinstance(p, dict) or not p.get('name') or protected(p['name']) for p in packages):
        raise CacheAbort('Invalid or protected overlay distribution in manifest')
    names = [canonical(p['name']) for p in packages]
    for package in packages:
        info = package.get('overlay_metadata_dir', '')
        if (not isinstance(info, str) or '/' in info or '\\' in info or not info.endswith('.dist-info')
                or not isinstance(package.get('version'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', str(package.get('record_sha256', '')))):
            raise CacheAbort('Invalid overlay distribution identity/path')
    if len(set(names)) != len(names) or sorted(names) != sorted(manifest.get('changed_distributions', [])):
        raise CacheAbort('Changed distribution list does not match archive metadata')
    check_compatibility(manifest.get('base_before', {}), manifest.get('base_after', {}), names)


def preflight_original(original, report: dict) -> dict:
    try:
        framework = original.preflight(report)
    except original.TestAbort as error:
        raise CacheAbort(str(error)) from error
    gpu = report['gpu']
    if 'A100' not in str(gpu.get('name', '')):
        raise CacheAbort('This dependency benchmark requires an assigned A100; no alternate GPU benchmark')
    return {'machine': platform.machine(), 'system': platform.system(),
            'python_version': platform.python_version(), 'python_major_minor': [sys.version_info.major, sys.version_info.minor],
            'python_abi': sysconfig.get_config_var('SOABI'), 'python_cache_tag': sys.implementation.cache_tag,
            'torch': framework['torch'], 'torchvision': framework['torchvision'],
            'cuda': gpu['torch_cuda'], 'numpy': metadata.version('numpy')}


def require_fresh_workspace(original) -> None:
    for path in [BENCH, COMFY, original.OUTPUT_PNG, original.RESULT_JSON]:
        if path.exists() or path.is_symlink():
            raise CacheAbort('Benchmark artifacts already exist; use a genuinely new runtime, no automatic deletion')


def subprocess_environment(*, restore: bool) -> dict:
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'GIT_TERMINAL_PROMPT': '0',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_SYSTEM': '/dev/null',
           'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}
    for name in ['HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'HUGGINGFACEHUB_API_TOKEN']:
        env.pop(name, None)
    if restore:
        env.update({'PYTHONPATH': str(OVERLAY) + os.pathsep + env.get('PYTHONPATH', ''),
                    'PIP_NO_INDEX': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'UV_OFFLINE': '1'})
    return env


def run_subprocess(mode: str, *, benchmark_started: float | None = None) -> dict:
    if mode not in {'validate', 'infer'}:
        raise CacheAbort('Unknown internal subprocess mode')
    script = str(Path(__file__).resolve())
    code = ('import importlib.util; s=importlib.util.spec_from_file_location("walter_cache_child", ' + repr(script) + '); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.run_child(' + repr(mode) + ')')
    log = BENCH / (mode + '.log')
    started = time.perf_counter()
    first_png = None
    output = CONTENT / 'walter-qwen-image-test.png'
    with log.open('w', encoding='utf-8') as handle:
        process = subprocess.Popen([sys.executable, '-B', '-c', code], env=subprocess_environment(restore=mode == 'infer'),
                                   stdout=handle, stderr=subprocess.STDOUT, cwd=CONTENT)
        try:
            while True:
                if mode == 'infer' and first_png is None and output.is_file():
                    first_png = time.perf_counter()
                returncode = process.poll()
                if returncode is not None:
                    break
                if time.perf_counter() - started > (3600 if mode == 'validate' else 7200):
                    raise CacheAbort('Bounded child execution timed out; no fallback')
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    if returncode:
        raise CacheAbort('Fresh ' + mode + ' subprocess failed; inspect local ' + mode + '.log')
    result = read_manifest(BENCH / (mode + '-child-result.json'))
    if result.get('status') != 'success':
        raise CacheAbort('Fresh subprocess did not return verified success')
    result['child_wall_seconds'] = round(time.perf_counter() - started, 4)
    if mode == 'infer':
        if first_png is None or benchmark_started is None:
            raise CacheAbort('PNG completion was not observed from a fresh output target')
        result['total_until_png_observed_seconds'] = round(first_png - benchmark_started, 4)
        result['png_observation_interval_seconds'] = 0.1
    return result


def run_child(mode: str) -> None:
    """Fresh interpreter only. No pip/git networking, even in .pth handlers."""
    require_colab()
    started = time.perf_counter()
    original = load_original()
    install_child_audit_guard(original)
    context_path = BENCH / ('validation-context.json' if mode == 'validate' else MANIFEST_NAME)
    manifest = read_manifest(context_path)
    if mode == 'validate':
        validate_context(manifest, original)
        check_compatibility(manifest['base_before'], manifest['base_after'], manifest['changed_distributions'])
    else:
        validate_manifest(manifest, original)
    result = {'status': 'running', 'mode': mode, 'network_installs_permitted': False}
    try:
        if mode == 'validate':
            original.setup_dependencies({name: metadata.version(name) for name in ['torch', 'torchvision']}, skip_setup=True)
            original.load_nodes()  # GPU imports must be isolated from build parent.
            result['packages'] = {name: metadata.version(name) for name in ['torch', 'torchvision', 'gguf', 'transformers',
                                  'huggingface-hub', 'safetensors', 'comfy-kitchen', 'comfy-aimdo', 'Pillow', 'numpy']}
        elif mode == 'infer':
            activate_overlay(OVERLAY)
            result['overlay_distributions_verified'] = verify_overlay(manifest['packages'], OVERLAY)
            result['bootstrap_seconds'] = round(time.perf_counter() - started, 4)
            if call_original_no_install(original) != 0:
                raise CacheAbort('Original main([]) inference failed; no alternate settings used')
            inference = read_manifest(original.RESULT_JSON)
            if any(inference.get(key) != value for key, value in original.request_manifest().items()):
                raise CacheAbort('Original result did not preserve every immutable request field')
            result['output'] = verify_inference_evidence(inference, original.request_manifest(), COMFY / 'models', original.OUTPUT_PNG)
            result['model_files_verified_by_original_sha256'] = inference['model_files_verified']
            result['model_hash_note'] = 'Real hashes computed by the unchanged original before inference; not rehashed a second time'
            result['original_timings_seconds'] = inference['timings_seconds']
            result['original_result_json'] = str(original.RESULT_JSON)
            result['code_revisions_verified'] = inference['code_revisions']
            result['overlay_distributions_verified_after'] = verify_overlay(manifest['packages'], OVERLAY)
        else:
            raise CacheAbort('Unknown internal subprocess mode')
        result['status'] = 'success'
    finally:
        result['elapsed_seconds'] = round(time.perf_counter() - started, 4)
        atomic_json(BENCH / (mode + '-child-result.json'), result)


def build_cache(report: dict) -> None:
    require_colab()
    store = require_store()
    storage_mode = 'drive' if os.environ.get('WALTER_COLAB_CACHE_DIR') is None else 'local_staging'
    storage_label = 'drive' if storage_mode == 'drive' else 'local_store'
    report.update({'storage_mode': storage_mode, 'cache_store_path': str(store)})
    original = load_original()
    require_fresh_workspace(original)
    if (store / ARCHIVE_NAME).exists() or (store / MANIFEST_NAME).exists():
        raise CacheAbort('Cache store already exists; never overwrite an earlier benchmark')
    with measured(report, 'preflight'):
        base_before = preflight_original(original, report)
    BENCH.mkdir(parents=True)
    original.WORK.mkdir(parents=True, exist_ok=True)
    with measured(report, 'snapshot_before'):
        before = snapshot_distributions()
        atomic_json(BENCH / 'distributions-before.json', before)
    # Exact same installer/requirements/revisions. Add strict constraints for ALL
    # supplied framework/CUDA distributions; do not package or replace them.
    framework = {name: value['version'] for name, value in before.items() if protected(name)}
    framework.update({name: base_before[name] for name in ['torch', 'torchvision']})
    with measured(report, 'installation'):
        original.setup_dependencies(framework, skip_setup=False)
    with measured(report, 'snapshot_after'):
        after = snapshot_distributions()
        atomic_json(BENCH / 'distributions-after.json', after)
        changed = changed_distributions(before, after)
    base_after = {**base_before, 'torch': after['torch']['version'], 'torchvision': after['torchvision']['version'],
                  'numpy': after['numpy']['version']}
    check_compatibility(base_before, base_after, changed)
    manifest = {'schema': SCHEMA, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'storage_mode': storage_mode, 'cache_store_path': str(store),
                'original_script_sha256': ORIGINAL_SHA256, 'cache_script_sha256': sha256_file(Path(__file__).resolve()),
                'request': original.request_manifest(), 'code_revisions': original.request_manifest()['code_revisions'],
                'base_before': base_before, 'base_after': base_after, 'changed_distributions': changed,
                'packages': [], 'files': {}}
    # Validation context contains actual versions/revisions only. No fake
    # archive size/hash, even temporarily: the archive does not yet exist.
    atomic_json(BENCH / 'validation-context.json', manifest)
    with measured(report, 'validation'):
        validation = run_subprocess('validate')
        for name in ['torch', 'torchvision']:
            if validation['packages'][name] != base_before[name]:
                raise CacheAbort('Fresh validation detected a framework version change')
    with measured(report, 'archive_build'):
        sources, packages, skipped = package_sources(changed, after)
        sources.update(repository_sources(COMFY, 'code/ComfyUI', original.COMFY_REVISION,
                                          'https://github.com/Comfy-Org/ComfyUI.git'))
        sources.update(repository_sources(GGUF, 'code/ComfyUI/custom_nodes/ComfyUI-GGUF', original.GGUF_REVISION,
                                          'https://github.com/leejet/ComfyUI-GGUF.git'))
        archive = BENCH / ARCHIVE_NAME
        manifest['files'] = write_archive(archive, sources)
        manifest['packages'] = packages
        manifest['excluded_entries'] = skipped
        manifest['archive'] = {'filename': ARCHIVE_NAME, 'size_bytes': archive.stat().st_size,
                               'sha256': sha256_file(archive), 'compression_level': 1,
                               'unpacked_size_bytes': sum(s['size_bytes'] for s in manifest['files'].values()),
                               'file_count': len(manifest['files']),
                               'local_path': str(archive),
                               ('drive_path' if storage_mode == 'drive' else 'store_path'): str(store / ARCHIVE_NAME)}
        validate_manifest(manifest, original)
        atomic_json(BENCH / MANIFEST_NAME, manifest)
    report['stage'] = storage_label + '_copy_and_verification'
    copied, verified = copy_and_verify(archive, store / ARCHIVE_NAME, manifest['archive']['sha256'])
    report['timings_seconds'][storage_label + '_copy'] = copied
    report['timings_seconds'][storage_label + '_verification'] = verified
    with measured(report, storage_label + '_manifest_copy_and_verification'):
        copy_and_verify(BENCH / MANIFEST_NAME, store / MANIFEST_NAME, sha256_file(BENCH / MANIFEST_NAME))
        if read_manifest(store / MANIFEST_NAME) != manifest:
            raise CacheAbort('Cache store manifest JSON readback differs')
    report.update({'archive': manifest['archive'],
                   ('manifest_drive_path' if storage_mode == 'drive' else 'manifest_store_path'): str(store / MANIFEST_NAME),
                   'manifest_sha256': sha256_file(store / MANIFEST_NAME), 'base_before': base_before, 'base_after': base_after,
                   'changed_distribution_count': len(changed), 'changed_distributions': packages,
                   'code_revisions': manifest['code_revisions'], 'validation': validation,
                   'torch_nvidia_unchanged_by_version_and_record': True, 'models_archived': False,
                   storage_label + '_sha256_independent_readback_verified': True})


def restore_cache(report: dict, benchmark_started: float) -> None:
    require_colab()
    store = require_store()
    storage_mode = 'drive' if os.environ.get('WALTER_COLAB_CACHE_DIR') is None else 'local_staging'
    storage_label = 'drive' if storage_mode == 'drive' else 'local_store'
    report.update({'storage_mode': storage_mode, 'cache_store_path': str(store)})
    original = load_original()
    require_fresh_workspace(original)
    with measured(report, 'manifest_and_compatibility'):
        manifest = read_manifest(store / MANIFEST_NAME)
        validate_manifest(manifest, original)
        current_base = preflight_original(original, report)
        check_compatibility(manifest['base_before'], current_base, manifest['changed_distributions'])
    # Compatibility passed BEFORE copying any archive or creating an overlay.
    BENCH.mkdir(parents=True)
    atomic_json(BENCH / MANIFEST_NAME, manifest)
    archive = BENCH / ARCHIVE_NAME
    report['stage'] = storage_label + '_copy_and_verification'
    copied, verified = copy_and_verify(store / ARCHIVE_NAME, archive, manifest['archive']['sha256'])
    report['timings_seconds'][storage_label + '_copy'] = copied
    report['timings_seconds']['archive_sha256_verification'] = verified
    if archive.stat().st_size != manifest['archive']['size_bytes']:
        raise CacheAbort('Copied archive byte size differs')
    with measured(report, 'extraction_and_file_hashes'):
        staging = BENCH / 'extracted'
        secure_extract(archive, staging, manifest['files'])
        COMFY.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging / 'code' / 'ComfyUI'), str(COMFY))
        if (staging / 'packages').is_dir():
            shutil.move(str(staging / 'packages'), str(OVERLAY))
        else:
            OVERLAY.mkdir()
    report['timings_seconds']['restore_overhead_before_child'] = round(time.perf_counter() - benchmark_started, 4)
    report['stage'] = 'original_inference_fresh_subprocess'
    child = run_subprocess('infer', benchmark_started=benchmark_started)
    timings = child['original_timings_seconds']
    report['timings_seconds'].update({
        'child_bootstrap_and_overlay_validation': child['bootstrap_seconds'],
        'restore_overhead_before_original_main': round(report['timings_seconds']['restore_overhead_before_child'] + child['bootstrap_seconds'], 4),
        'imports_and_node_validation': timings['dependencies'],
        'model_download_and_sha256': timings['model_download_and_hash'],
        'inference_and_export': round(sum(timings[k] for k in ['text_encode', 'diffusion_load', 'sampling', 'vae_decode', 'export_png']), 4),
        'total_until_png_observed': child['total_until_png_observed_seconds'], 'child_wall': child['child_wall_seconds']})
    with measured(report, 'final_png_independent_verification'):
        report['output'] = verify_png(original.OUTPUT_PNG, original.WIDTH, original.HEIGHT, child['output'])
    report.update({'archive': manifest['archive'], 'base_current': current_base,
                   'base_cached_before': manifest['base_before'], 'base_cached_after': manifest['base_after'],
                   'child': child, 'original_timings_seconds': timings, 'code_revisions': manifest['code_revisions'],
                   'changed_distribution_count': len(manifest['packages']), 'network_installs_permitted': False,
                   'models_archived': False, 'fresh_artifact_targets_verified': True,
                   'runtime_freshness_note': 'Parent must actually provision a new runtime; artifact absence alone does not prove runtime identity',
                   'time_to_png_note': 'Observed filesystem rename in parent, 0.1s polling granularity; excludes final independent verification'})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'restore'])
    options = parser.parse_args(argv)
    try:
        require_colab()  # BEFORE writes, runtime-script import, mounts, or GPU probes.
        store = require_store()
    except CacheAbort as error:
        print(str(error), file=sys.stderr)
        return 2
    path = BUILD_JSON if options.mode == 'build' else RESTORE_JSON
    if path.exists() or path.is_symlink():
        print('Existing benchmark result JSON will not be overwritten; use a new Colab runtime', file=sys.stderr)
        return 2
    report = {'status': 'running', 'stage': 'initialization', 'mode': options.mode,
              'storage_mode': 'drive' if os.environ.get('WALTER_COLAB_CACHE_DIR') is None else 'local_staging',
              'cache_store_path': str(store),
              'started_at_utc': datetime.now(timezone.utc).isoformat(), 'timings_seconds': {},
              'cache_script_sha256': sha256_file(Path(__file__).resolve()),
              'original_script_sha256': ORIGINAL_SHA256,
              'benchmark_executed': False}
    started = time.perf_counter()
    try:
        if options.mode == 'build':
            build_cache(report)
        else:
            restore_cache(report, started)
        report['status'] = 'success'
        report['stage'] = 'complete'
        report['benchmark_executed'] = True
        return 0
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = {'type': type(error).__name__, 'message': str(error) if isinstance(error, CacheAbort)
                           else 'Failure at recorded stage; inspect local logs, no fallback performed'}
        return 1
    finally:
        report['timings_seconds']['total'] = round(time.perf_counter() - started, 4)
        report['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        atomic_json(path, report)
        print_summary(options.mode, report, path)


if __name__ == '__main__':
    raise SystemExit(main())
