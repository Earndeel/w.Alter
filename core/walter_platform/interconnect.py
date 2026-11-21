"""Interconnection rule: a module reaches another only through a declared interface.

Interfaces: a command on the PATH, HTTP, MCP, a bus event, or a file the provider declares public in its
contract (``public``), located by walter-core through the path resolver. What this check rejects is the
hidden coupling: a module's code or configuration naming another module's directory (its legacy root
``/opt/walter-<x>`` or its ``/walter/<target>``), whether to import its code, run its programs or read
its files. Modules sharing a root (memory, logs, bus) form one home and may reference each other.

Static and read-only: files are scanned as text, nothing is imported or executed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from . import paths

SKIP_DIRS = {'venv', '.venv', 'node_modules', '.git', '__pycache__', '.worktrees', '.pytest_cache', '.cache',
             'tests', 'test', 'bench', 'docs', 'reports', 'evidence', 'fixtures', 'state', 'cache', 'models',
             'contracts', 'build', 'skills', 'archive', 'python', 'mcp', 'locks', 'outputs', 'dist'}
SKIP_FILES = {'registry.json', 'catalog.json', 'release-sources.json', 'contracts.generated.md'}
TEXT_SUFFIXES = {'.py', '.sh', '.toml', '.json', '.yaml', '.yml', '.mjs', '.js', '.cjs', '.ts', '.env', '.conf', '.cfg', ''}
MAX_BYTES = 1024 * 1024


def _homes(catalog=None, filesystem='/'):
    """Module id -> (home root, every path that designates it). Modules sharing a root share a home."""
    entries = paths._catalog(catalog)
    homes = {}
    for name, item in entries.items():
        names = {str(paths.target_root(item))}
        legacy = paths.legacy_root(item)
        if legacy is not None:
            names.add(str(legacy))
        homes[name] = (str(paths.resolve(item, filesystem=filesystem)), names)
    return homes


def _files(root, nested=()):
    """Text files of a module home; homes nested inside it (router/llm) are scanned as their own home."""
    base = Path(root)
    nested = {Path(n) for n in nested}
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')
                         and Path(folder) / d not in nested)
        for name in sorted(files):
            p = Path(folder) / name
            if name in SKIP_FILES or p.suffix not in TEXT_SUFFIXES or p.is_symlink():
                continue
            try:
                if p.stat().st_size <= MAX_BYTES:
                    yield p
            except OSError:
                continue


def scan(*, catalog=None, filesystem='/'):
    homes = _homes(catalog, filesystem)
    # Longest designations first, so a nested target is not read as its parent module.
    designations = sorted(((d, name) for name, (_, ds) in homes.items() for d in ds), key=lambda x: -len(x[0]))
    pattern = re.compile('|'.join(re.escape(d) + r'(?![A-Za-z0-9_-])' for d, _ in designations))
    owner_of = dict(designations)
    violations, scanned = [], set()
    for name, (root, _) in sorted(homes.items()):
        if root in scanned:
            continue
        scanned.add(root)
        own = {n for n, (r, _) in homes.items() if r == root}
        real = Path(filesystem) / root.lstrip('/')
        if not real.is_dir():
            continue
        nested = [Path(filesystem) / r.lstrip('/') for r, _ in homes.values() if r != root and r.startswith(root + '/')]
        for f in _files(real, nested):
            try:
                text = f.read_text(errors='replace')
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for m in pattern.finditer(line):
                    target = owner_of[m.group(0)]
                    if target in own or homes[target][0] == root:
                        continue
                    violations.append({'from': sorted(own)[0] if len(own) == 1 else '+'.join(sorted(own)),
                                       'to': target, 'file': str(PurePosixPath(root) / f.relative_to(real)),
                                       'line': number, 'text': line.strip()[:160]})
    return {'ok': not violations, 'rule': 'a module reaches another only through a declared interface',
            'violations': violations,
            'pairs': sorted({f"{v['from']} -> {v['to']}" for v in violations})}
