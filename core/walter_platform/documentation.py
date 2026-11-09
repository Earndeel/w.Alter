"""Documentation invariants (owner rule 2026-11-09: every module, significant component and annex folder is
self-describing). Read-only, built on the registry only (no second source): declared component paths, READMEs and
contracts exist; the module README carries the standard header. Findings are warnings until the existing stock is
caught up (before E1, see /walter/docs/DOCUMENTATION.md § 7); `enforce=True` turns them into failures.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import registry

# Standard header (README of a module or component): what it is, who answers for it, its real state, what it must not
# do, its contracts. French or English labels are accepted; a row is `| **Label** | … |`.
HEADER = {'role': ('rôle', 'role'), 'owner': ('propriétaire', 'owner'), 'status': ('état', 'status', 'statut'),
          'not': ('ne fait pas', 'does not'), 'contracts': ('contrats', 'contracts')}
ROW = re.compile(r'^\|\s*\*\*([^*|]+)\*\*\s*\|', re.M)


def header_fields(text: str) -> set[str]:
    labels = {m.group(1).strip().lower() for m in ROW.finditer(text[:6000])}
    return {key for key, names in HEADER.items() if any(n in labels for n in names)}


def scan(path=None, *, enforce=False):
    mods = registry.load(path)['modules']
    findings, components, readmes = [], 0, set()
    for m in mods:
        root = Path(m['root'])
        readme = root / 'README.md'
        if root not in {Path(x['root']) for x in mods if x['id'] < m['id']}:   # shared roots counted once
            if not readme.exists():
                findings.append({'module': m['id'], 'kind': 'module_readme_missing', 'path': str(readme)})
            else:
                missing = sorted(set(HEADER) - header_fields(readme.read_text(errors='replace')))
                if missing:
                    findings.append({'module': m['id'], 'kind': 'module_header_incomplete', 'path': str(readme),
                                     'missing': missing})
        if not m.get('components'):
            findings.append({'module': m['id'], 'kind': 'components_undeclared'})
        for c in m.get('components', []):
            components += 1
            exists = Path(c['path']).exists()
            if c['status'] != 'planned' and not exists:
                findings.append({'module': m['id'], 'component': c['id'], 'kind': 'component_path_missing',
                                 'path': c['path']})
            for key in ('readme',):
                if c.get(key):
                    readmes.add(c[key])
                    if not Path(c[key]).exists():
                        findings.append({'module': m['id'], 'component': c['id'], 'kind': 'component_readme_missing',
                                         'path': c[key]})
            for ref in c.get('contracts', []):
                if not Path(ref).exists():
                    findings.append({'module': m['id'], 'component': c['id'], 'kind': 'component_contract_missing',
                                     'path': ref})
    blocking = [f for f in findings if f['kind'] in ('component_path_missing', 'component_readme_missing',
                                                     'component_contract_missing')]
    return {'ok': not (findings if enforce else blocking), 'mode': 'enforce' if enforce else 'warn',
            'rule': 'self-describing modules and components (owner rule 2026-11-09)',
            'components': components, 'readmes': len(readmes), 'findings': findings,
            'summary': {k: sum(f['kind'] == k for f in findings) for k in sorted({f['kind'] for f in findings})}}
