"""Exposure rule (2026-11-27, S0 of the Python security study): no credential file is readable by every user.

A world-readable file whose name says it holds credentials (``.env``, ``*.env``, ``credentials*.json``, ``*.pem``,
``*.key``, token files…) and whose content carries a real value (an assignment of a key/token/secret/password to a
non-placeholder value, a known key prefix, a private-key header) fails ``walter check``. An unprivileged process (the
Python kernel bubble, a service user) could read it.

Static, read-only, cheap: only candidate names are opened, never printed — findings carry the path and a count.
Roots: the Walter tree, the instance, and the host's project / app / service folders (``WALTER_EXPOSURE_ROOTS``
overrides, ``:``-separated).
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

DEFAULT_ROOTS = ('/projects', '/apps', '/services')
SKIP_DIRS = {'node_modules', '.git', 'venv', '.venv', 'site-packages', '__pycache__', '.worktrees', 'python', 'tests',
             'test', 'fixtures', 'cargo-home', '.cache', 'dist', 'build'}
NAME = re.compile(r'(^\.env(\..+)?$|\.env$|^credentials.*\.json$|\.pem$|\.key$|token(s)?(\.txt|\.json)?$'
                  r'|^secrets?\.(json|toml|ya?ml|txt)$|^\.pgpass$|^\.netrc$)', re.I)
PLACEHOLDER = re.compile(r'^(|changeme|change_me|xxx+|\*+|<.*>|\$\{.*\}|your[_-].*|example.*|dummy.*|test.*|none|null'
                         r'|true|false|\d{1,6})$', re.I)
ASSIGN = re.compile(r'^\s*(?:export\s+)?[A-Za-z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PASS|PWD|CREDENTIALS?)'
                    r'[A-Za-z0-9_]*\s*[=:]\s*["\']?([^"\'#\s]*)', re.I)
PREFIX = re.compile(r'(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}'
                    r'|xox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')
EXAMPLE = re.compile(r'\.(example|sample|template|dist|tmpl)$|\.(example|sample)\.', re.I)
MAX_BYTES = 256 * 1024


def roots():
    env = os.environ.get('WALTER_EXPOSURE_ROOTS')
    if env:
        return [Path(p) for p in env.split(':') if p]
    out = []
    try:
        from . import paths
        out.append(Path(paths.walter_root()))
    except Exception:
        pass
    try:
        from . import instance
        out.append(Path(instance.root()))
    except Exception:
        pass
    return out + [Path(p) for p in DEFAULT_ROOTS]


def secrets_in(text):
    """How many lines carry a real credential value (placeholders and empty values do not count)."""
    n = 0
    for line in text.splitlines():
        if PREFIX.search(line):
            n += 1
            continue
        m = ASSIGN.match(line)
        if m and not PLACEHOLDER.match(m.group(2)) and len(m.group(2)) >= 8:
            n += 1
    return n


def scan(root_list=None):
    findings, seen = [], set()
    for root in root_list or roots():
        if not root.is_dir():
            continue
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if not NAME.search(name) or EXAMPLE.search(name):
                    continue
                p = Path(folder) / name
                try:
                    st = p.lstat()
                    if not stat.S_ISREG(st.st_mode) or not st.st_mode & stat.S_IROTH or st.st_size > MAX_BYTES:
                        continue
                    real = p.resolve()
                    if real in seen:
                        continue
                    seen.add(real)
                    n = secrets_in(p.read_text(errors='replace'))
                except OSError:
                    continue
                if n:
                    findings.append({'path': str(p), 'mode': oct(st.st_mode & 0o777), 'lines': n})
    return {'ok': not findings, 'rule': 'credential files are never world-readable (chmod 600)',
            'findings': sorted(findings, key=lambda f: f['path'])}
