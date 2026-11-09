#!/usr/bin/env python3
"""Fingerprints of the frozen engine kernel (lot E1): one SHA-256 per installed npm package (files, modes, links),
plus the composition files the kernel runs with and the configuration DSH composes from them (`--dump-config` of each
profile, hashed, never printed). Standard library only, read-only.

    verify.py snapshot <install-dir> [--home DSH_HOME]   print the manifest (JSON) of an installation
    verify.py check <install-dir> [--home DSH_HOME]      compare with kernel/installed.json, exit 1 on drift

The manifest is the source of truth for "is this the frozen kernel"; package-lock.json gives the registry
integrity of each tarball, this file the integrity of what is actually installed (install scripts included).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'installed.json'
COMPOSITION_FILES = ('cordis.patch.yml', 'walter-hooks.json', 'profiles/web/cordis.patch.yml',
                     'profiles/web/cordis.yml', 'profiles/headless/cordis.patch.yml', 'profiles/headless/cordis.yml')


def _tree(root: Path) -> str:
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        base = Path(dirpath)
        for name in sorted(filenames + [d for d in dirnames if (base / d).is_symlink()]):
            p = base / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                h.update(f'L {rel} {os.readlink(p)}\n'.encode())
            elif p.is_file():
                fh = hashlib.sha256(p.read_bytes()).hexdigest()
                h.update(f'F {rel} {fh} {"x" if os.access(p, os.X_OK) else "-"}\n'.encode())
    return h.hexdigest()


def packages(install: Path) -> dict[str, str]:
    nm = install / 'node_modules'
    out = {}
    for entry in sorted(nm.iterdir()):
        if entry.name.startswith('@') and entry.is_dir() and not entry.is_symlink():
            for sub in sorted(entry.iterdir()):
                out[f'{entry.name}/{sub.name}'] = _tree(sub) if sub.is_dir() else 'not-a-dir'
        elif entry.name == '.bin':
            out['.bin'] = _tree(entry)
        elif entry.is_dir() and not entry.name.startswith('.'):
            out[entry.name] = _tree(entry)
    return out


def composed(install: Path, home: Path) -> dict[str, str]:
    """SHA-256 of `dsh --profile <p> --dump-config` for every profile of the home (deterministic, checked twice)."""
    out = {}
    profiles = home / 'profiles'
    for prof in sorted(p.name for p in profiles.iterdir() if p.is_dir()) if profiles.is_dir() else []:
        run = subprocess.run([str(install / 'node_modules' / '.bin' / 'dsh'), '--profile', prof, '--dump-config'],
                             env={**os.environ, 'DSH_HOME': str(home)}, capture_output=True, timeout=120)
        out[prof] = hashlib.sha256(run.stdout).hexdigest() if run.returncode == 0 else f'error {run.returncode}'
    return out


def snapshot(install: Path, home: Path | None) -> dict:
    lock = json.loads((install / 'package-lock.json').read_text())
    root = lock['packages']['node_modules/@deepseek-ai/dsh']
    data = {'kernel': '@deepseek-ai/dsh', 'version': root['version'], 'integrity': root['integrity'],
            'lock_sha256': hashlib.sha256((install / 'package-lock.json').read_bytes()).hexdigest(),
            'node': os.popen('node --version').read().strip(), 'packages': packages(install)}
    if home:
        data['compositions'] = {f: hashlib.sha256((home / f).read_bytes()).hexdigest()
                                for f in COMPOSITION_FILES if (home / f).is_file()}
        data['composed'] = composed(install, home)
    return data


def check(install: Path, home: Path | None) -> dict:
    want = json.loads(MANIFEST.read_text())
    got = snapshot(install, home)
    wp, gp = want['packages'], got['packages']
    report = {'version': got['version'] == want['version'], 'integrity': got['integrity'] == want['integrity'],
              'missing': sorted(set(wp) - set(gp)), 'extra': sorted(set(gp) - set(wp)),
              'changed': sorted(k for k in set(wp) & set(gp) if wp[k] != gp[k])}
    if home and 'compositions' in want:
        wc, gc = want['compositions'], got.get('compositions', {})
        report['compositions_changed'] = sorted(k for k in set(wc) | set(gc) if wc.get(k) != gc.get(k))
    if home and 'composed' in want:
        wd, gd = want['composed'], got.get('composed', {})
        report['composed_changed'] = sorted(k for k in set(wd) | set(gd) if wd.get(k) != gd.get(k))
    report['ok'] = (report['version'] and report['integrity'] and not report['missing'] and not report['extra']
                    and not report['changed'] and not report.get('compositions_changed')
                    and not report.get('composed_changed'))
    return report


def main(argv):
    if len(argv) < 2 or argv[0] not in ('snapshot', 'check'):
        print(__doc__)
        return 2
    home = Path(argv[argv.index('--home') + 1]) if '--home' in argv else None
    install = Path(argv[1])
    if argv[0] == 'snapshot':
        print(json.dumps(snapshot(install, home), indent=1, sort_keys=True))
        return 0
    result = check(install, home)
    print(json.dumps(result, indent=1))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
