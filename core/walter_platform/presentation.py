"""How each module presents itself to agents, from files in its own folder (`<module>/manifest/`).

M0      — `manifest/SUMMARY.md`: one line (what it does + the tool to open), always present.
Level 1 — `manifest/MANIFEST.md`: what the module is, how it is organised, how to use it. Injected for every
          harness plugged into W.Alter (walter-context composes the layer). A module whose level 1 depends on live
          data declares `manifest_command`; its output is appended (router usage note, skills domain map).
Level 2 — index: what the module contains, produced and kept up to date by the module itself; paged, on demand.
Guide   — `manifest/GUIDE.md`: detailed reading on demand.
Level 3 is the item itself, through the module's own tools.

The contract's `presentation` block only points to these files and commands. Nothing here imports a module;
commands are the ones the contract declares on the PATH. Notes use the router's v1 envelope.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from . import registry

SUMMARY_MAX = 200        # M0: one line per module, always injected
MANIFEST_MAX = 3000      # M1 is injected: short by construction
GUIDE_MAX = 40000
COMMAND_TIMEOUT = 20
INDEX_LIMIT = 50


def _render(text: str) -> str:
    """Shipped texts say {{owner.address}}; the active instance fills it (neutral software)."""
    from . import instance
    try:
        return instance.render(text)
    except (OSError, ValueError, KeyError):
        return text


def _entries(audience: str | None = 'agent') -> list[dict]:
    rows = [m for m in registry.load()['modules'] if isinstance(m.get('presentation'), dict)
            and (audience is None or m['presentation'].get('audience') == audience)]
    return sorted(rows, key=lambda m: (m['presentation'].get('order', 50), m['id']))


def _entry(module: str) -> dict:
    for m in _entries(None):
        if m['id'] == module:
            return m
    raise ValueError('unknown module or module without presentation: ' + module)


def _demote(text: str, levels: int = 2) -> str:
    """A module's own headings become sub-sections of the layer (# → ###, ## → ####)."""
    return re.sub(r'^(#{1,4}) ', lambda m: '#' * min(6, len(m.group(1)) + levels) + ' ', text, flags=re.M)


def _command_text(args: list[str]) -> str:
    out = subprocess.run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    if out.returncode:
        raise RuntimeError('manifest command failed')
    text = out.stdout.strip()
    try:  # a v1 note envelope (router brief --json) or plain text
        doc = json.loads(text)
        if isinstance(doc, dict) and isinstance(doc.get('content'), str):
            return doc['content'].strip()
    except ValueError:
        pass
    return text


def envelope(module: str, content: str, tools: list[str], level: str = 'M1') -> dict:
    kind = {'M0': 'summary', 'M1': 'manifest'}[level]
    return {'schema_version': 1, 'note_version': 1, 'id': f'walter-{module}.{kind}', 'module': module, 'level': level,
            'format': 'text/markdown', 'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest(),
            'chars': len(content), 'required_tools': list(tools), 'placement': 'stable_capabilities',
            'refresh': 'next_owner_message', 'source': {'command': 'walter', 'args': ['present', 'note', module]}}


def manifest(module: str) -> str:
    """Level 1 text of one module: its manifest file, then the live part it generates, owner placeholders filled."""
    p = _entry(module)['presentation']
    text = Path(p['manifest']).read_text().strip()
    if len(text) > MANIFEST_MAX:
        raise ValueError(module + ' manifest exceeds ' + str(MANIFEST_MAX) + ' characters (level 1 is injected)')
    if not text.startswith('# '):
        text = '# ' + p['title'] + '\n\n' + text
    if p.get('manifest_command'):
        text += '\n\n' + _demote(_command_text(p['manifest_command']), 1)
    return _render(text)


def summary(module: str) -> str:
    """M0: the module's one line (manifest/SUMMARY.md), owner placeholders filled."""
    p = _entry(module)['presentation']
    if not p.get('summary'):
        raise ValueError(module + ' has no M0 summary')
    text = ' '.join(Path(p['summary']).read_text().split())
    if not text or len(text) > SUMMARY_MAX:
        raise ValueError(module + ' summary must be one line of 1-' + str(SUMMARY_MAX) + ' characters')
    return _render(text)


def note(module: str, level: str = 'M1') -> dict:
    """M0 (`- **Title** — line`) or M1 (manifest, headings demoted under the layer header) in the v1 envelope."""
    p = _entry(module)['presentation']
    if level == 'M0':
        return envelope(module, f"- **{_render(p['title'])}** — {summary(module)}", p.get('tools') or [], 'M0')
    return envelope(module, _demote(manifest(module)), p.get('tools') or [], 'M1')


FORMS = ('full', 'm0')


def notes(form: str = 'full', m1: list[str] | None = None) -> dict:
    """Every agent-facing module's presentation, in presentation order; a failing module is reported, never hidden.

    form='full' (default, current layer): M1 for every module.
    form='m0': M0 for every module, plus M1 for the modules listed in `m1` (the ones the context plan judges useful).
    """
    if form not in FORMS:
        raise ValueError('form must be one of ' + ', '.join(FORMS))
    wanted = set(m1 or [])
    out, problems = [], []
    for m in _entries():
        levels = ['M1'] if form == 'full' else ['M0'] + (['M1'] if m['id'] in wanted else [])
        for level in levels:
            try:
                out.append(note(m['id'], level))
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                problems.append({'module': m['id'], 'level': level, 'error': type(exc).__name__,
                                 'detail': str(exc)[:200]})
    known = {m['id'] for m in _entries()}
    problems += [{'module': x, 'level': 'M1', 'error': 'UnknownModule'} for x in sorted(wanted - known)]
    return {'schema_version': 1, 'form': form, 'm1': sorted(wanted & known), 'notes': out, 'problems': problems}


def catalog() -> dict:
    """Agent-facing modules, where their presentation lives and which levels they offer."""
    rows = []
    for m in _entries():
        p = m['presentation']
        rows.append({'module': m['id'], 'title': _render(p['title']), 'summary': p.get('summary'),
                     'manifest': p['manifest'],
                     'guide': p.get('guide'), 'index': bool(p.get('index')),
                     'index_sections': (p.get('index') or {}).get('sections', ''), 'tools': p.get('tools') or []})
    return {'modules': rows}


def guide(module: str) -> str:
    """Detailed reading of a module, on demand."""
    p = _entry(module)['presentation']
    if not p.get('guide'):
        return manifest(module)
    text = Path(p['guide']).read_text()
    if len(text) > GUIDE_MAX:
        raise ValueError(module + ' guide exceeds ' + str(GUIDE_MAX) + ' characters')
    return _render(text)


def index(module: str, section: str = '', offset: int = 0, limit: int = 20) -> dict:
    """Level 2: run the module's declared index command; page a plain list when the module does not."""
    p = _entry(module)['presentation']
    spec = p.get('index')
    if not spec:
        return {'module': module, 'index': None, 'hint': 'Ce module n’a pas d’index ; son guide : module_guide.'}
    offset, limit = max(0, int(offset)), max(1, min(int(limit), INDEX_LIMIT))
    args = list(spec['command'])
    if section:
        if not spec.get('section_arg'):
            raise ValueError(module + ' index has no sections')
        args += [spec['section_arg'], section]
    if spec.get('paged'):
        args += ['--offset', str(offset), '--limit', str(limit)]
    out = subprocess.run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    if out.returncode:
        raise RuntimeError(module + ' index command failed')
    data = json.loads(out.stdout)
    if isinstance(data, list) and not spec.get('paged'):
        end = offset + limit
        data = {'entries': data[offset:end], 'total': len(data), 'offset': offset,
                'next_offset': end if end < len(data) else None}
    return {'module': module, 'section': section or None, 'index': data}
