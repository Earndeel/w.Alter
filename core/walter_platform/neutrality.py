"""Neutrality rule: shipped software carries no instance data and no host-specific home.

A module's files must not contain the active instance's private markers (owner's address form, name, e-mails,
declared markers — read from the instance, so the rule holds for any instance) nor assume the single-root host
(``/root``). Docs and tests ship with the software, so they are scanned too; instance content (skills library,
reports, state, generated builds) is not software and is skipped.

Modules flagged ``"neutral": true`` in the catalog must be clean: a finding there fails ``walter check``. Other
modules are reported (counts per module) until their lot makes them neutral. Static and read-only.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from . import instance, paths

SKIP_DIRS = {'venv', '.venv', 'node_modules', '.git', '__pycache__', '.worktrees', '.pytest_cache', '.cache',
             'bench', 'reports', 'evidence', 'state', 'cache', 'models', 'build', 'skills', 'archive', 'python',
             'mcp', 'locks', 'outputs', 'dist', 'drafts', '.state'}
SKIP_FILES = {'registry.json', 'contracts.generated.md'}
TEXT_SUFFIXES = {'.py', '.sh', '.toml', '.json', '.yaml', '.yml', '.mjs', '.js', '.cjs', '.ts', '.env', '.conf',
                 '.cfg', '.md', '.txt', '.sql', '.html', '.service', '.timer', ''}
HOST_HOME = re.compile(r'(?<![A-Za-z0-9_.-])/root(?=/|\b)')
MAX_BYTES = 1024 * 1024


def _files(root, nested=()):
    nested = {Path(n) for n in nested}
    for folder, dirs, files in os.walk(root):
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


def _pattern(markers):
    if not markers:
        return None
    return re.compile('|'.join(r'(?<![A-Za-z0-9])' + re.escape(m) + r'(?![A-Za-z0-9])' for m in markers),
                      re.IGNORECASE)


def scan(*, catalog=None, filesystem='/', markers=None, instance_root=None):
    """Per module home: files with private markers and files assuming /root. Findings name files, not content."""
    if markers is None:
        try:
            markers = instance.markers(instance_root)
            source = 'instance'
        except (OSError, ValueError):
            markers, source = [], 'none (no active instance)'
    else:
        source = 'given'
    private = _pattern(markers)
    entries = paths._catalog(catalog)
    homes = {}
    for name, item in entries.items():
        homes.setdefault(str(paths.resolve(item, filesystem=filesystem)), []).append(name)
    modules, failures = [], []
    for root, owners in sorted(homes.items()):
        real = Path(filesystem) / root.lstrip('/')
        if not real.is_dir():
            continue
        neutral = any(entries[n].get('neutral') is True for n in owners)
        personal, host = [], []
        nested = [Path(filesystem) / r.lstrip('/') for r in homes if r != root and r.startswith(root + '/')]
        for f in _files(real, nested):
            try:
                text = f.read_text(errors='replace')
            except OSError:
                continue
            rel = str(PurePosixPath(root) / f.relative_to(real))
            if private is not None and private.search(text):
                personal.append(rel)
            if HOST_HOME.search(text):
                host.append(rel)
        row = {'module': '+'.join(sorted(owners)), 'root': root, 'neutral_required': neutral,
               'private_marker_files': len(personal), 'host_home_files': len(host)}
        if neutral:
            row['files'] = sorted(set(personal) | set(host))
            if personal or host:
                failures.append(row['module'])
        modules.append(row)
    return {'ok': not failures, 'rule': 'shipped software carries no instance data and no /root home',
            'markers_from': source, 'markers': len(markers), 'failing': failures, 'modules': modules}
