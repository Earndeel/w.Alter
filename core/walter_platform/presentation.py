"""How W.Alter, each module and each component present themselves to agents: one scale, three depths (lot 3c, 2026-11-24).

D1 — what the entity is (a definition) and how to open its D2. W.Alter: `/walter/docs/manifest/SUMMARY.md`;
     module: `manifest/SUMMARY.md`; component: its `role` in the module contract.
D2 — role, organisation, tools and interfaces, where to check the live state, and the children at their D1
     (generated from the registry). W.Alter: `/walter/docs/manifest/MANIFEST.md` + the modules; module:
     `manifest/MANIFEST.md` (+ the live part a module declares with `manifest_command`) + its components;
     component: its contract entry and its README header.
D3 — technical detail and sources. W.Alter: `/walter/docs/manifest/GUIDE.md`; module: `manifest/GUIDE.md`, else its
     README; component: its README.
`module_index` stays the module's live contents (paged, produced by the module itself).

Paths: `walter`, a module id, `module/component`. The contract's `presentation` block only points to these files and
commands; nothing here imports a module; commands are the ones the contract declares on the PATH. Notes use the
router's v1 envelope. Former names: M0 = D1 line, M1 = D2 card.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from . import paths, registry

SUMMARY_MAX = 320        # D1: a definition, clarity before brevity (owner, 2026-11-24); always injected
MANIFEST_MAX = 3000      # M1 is injected: short by construction
GUIDE_MAX = 40000
COMMAND_TIMEOUT = 20
INDEX_LIMIT = 50
ENTITY = 'walter'
DEPTHS = ('D1', 'D2', 'D3')


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
        return envelope(module, d1_line(module), p.get('tools') or [], 'M0')
    return envelope(module, _demote(manifest(module)), p.get('tools') or [], 'M1')


FORMS = ('full', 'm0')


def notes(form: str = 'full', m1: list[str] | None = None) -> dict:
    """Every agent-facing module's presentation, in presentation order; a failing module is reported, never hidden.

    form='full' (default, current layer): M1 for every module.
    form='m0': M0 for every module, plus M1 for the modules listed in `m1` (the ones the context plan judges useful).
    `m1` may name `walter` itself: its D2 comes first, as a note of module `walter`.
    """
    if form not in FORMS:
        raise ValueError('form must be one of ' + ', '.join(FORMS))
    wanted = set(m1 or [])
    out, problems = [], []
    if ENTITY in wanted:   # lot 3d: W.Alter's own D2 as a note, for a message about W.Alter itself
        try:
            out.append(envelope(ENTITY, _demote(d2(ENTITY)), [], 'M1'))
        except (OSError, ValueError, RuntimeError) as exc:
            problems.append({'module': ENTITY, 'level': 'M1', 'error': type(exc).__name__, 'detail': str(exc)[:200]})
    for m in _entries():
        levels = ['M1'] if form == 'full' else ['M0'] + (['M1'] if m['id'] in wanted else [])
        for level in levels:
            try:
                out.append(note(m['id'], level))
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                problems.append({'module': m['id'], 'level': level, 'error': type(exc).__name__,
                                 'detail': str(exc)[:200]})
    known = {m['id'] for m in _entries()} | {ENTITY}
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
    """D3 of a module: its guide, else its README (the module's own documentation, no copy)."""
    p = _entry(module)['presentation']
    if p.get('guide'):
        text = Path(p['guide']).read_text()
        if len(text) > GUIDE_MAX:
            raise ValueError(module + ' guide exceeds ' + str(GUIDE_MAX) + ' characters')
        return _render(text)
    readme = Path(_module(module)['root']) / 'README.md'
    if readme.is_file():
        return _clip_file(readme)
    return manifest(module)


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


# ---- One scale for every entity (lot 3c, 2026-11-24): walter, a module, a module's component ----

def _module(module_id: str) -> dict:
    modules = registry.load()['modules']
    for m in modules:
        if m['id'] == module_id:
            return m
    # a wrong guess answers with the right names, so the agent's next call can succeed (lot 3c: discovery failures)
    near = [f"{m['id']}/{c['id']}" for m in modules for c in m.get('components') or [] if c['id'] == module_id]
    raise ValueError(f"unknown module: {module_id}." + (f" Components with that name: {', '.join(near)}." if near else '')
                     + ' Modules: ' + ', '.join(m['id'] for m in modules) + '.')


def _walter_file(name: str) -> Path:
    return Path(str(paths.walter_root())) / 'docs' / 'manifest' / name


def _clip_file(path: Path) -> str:
    text = path.read_text(errors='replace')
    if len(text) > GUIDE_MAX:
        text = text[:GUIDE_MAX] + f'\n\n… [cut at {GUIDE_MAX} characters; the whole file: {path}]'
    return _render(text)


def resolve(path: str) -> dict:
    """`walter` | `<module>` | `<module>/<component>` → what it is (no file is read here)."""
    path = (path or ENTITY).strip().strip('/')
    if path == ENTITY:
        return {'kind': 'walter', 'path': ENTITY}
    module_id, _, component = path.partition('/')
    m = _module(module_id)
    if not component:
        return {'kind': 'module', 'path': module_id, 'module': m}
    for c in m.get('components') or []:
        if c['id'] == component:
            return {'kind': 'component', 'path': f"{module_id}/{component}", 'module': m, 'component': c}
    raise ValueError(f"unknown component of {module_id}: {component}. Its components: "
                     + ', '.join(c['id'] for c in m.get('components') or []) + '.')


def _definition(entity: dict) -> str:
    if entity['kind'] == 'walter':
        text = ' '.join(_walter_file('SUMMARY.md').read_text().split())
        if not text or len(text) > SUMMARY_MAX:
            raise ValueError('walter summary must be one line of 1-' + str(SUMMARY_MAX) + ' characters')
        return _render(text)
    if entity['kind'] == 'module':
        m = entity['module']
        if isinstance(m.get('presentation'), dict) and m['presentation'].get('summary'):
            return summary(m['id'])
        return (m.get('contract') or {}).get('purpose') or m['id']
    c = entity['component']
    return (c.get('role') or c['id']).rstrip('.') + '.'


def d1_line(path: str) -> str:
    """One line in a list of children: the path first, then the definition (the list's header says how to open D2)."""
    entity = resolve(path)
    if entity['kind'] == 'component':
        status = entity['component'].get('status')
        return f"- `{entity['path']}` — {_definition(entity)}" + (f" ({status})" if status and status != 'active' else '')
    return f"- `{entity['path']}` — {_definition(entity)}"


def d1(path: str = ENTITY) -> str:
    entity = resolve(path)
    return f'{_definition(entity)} D2: `module_guide("{entity["path"]}", depth="D2")`.'


def _children(entity: dict) -> str:
    if entity['kind'] == 'walter':
        lines = [d1_line(m['id']) for m in _entries()]
        return ('## Modules (D1; open one with `module_guide("<path>", depth="D2")`)\n' + '\n'.join(lines)) if lines else ''
    if entity['kind'] == 'module':
        comps = entity['module'].get('components') or []
        live = [c for c in comps if c.get('status') != 'obsolete']
        if not live:
            return ''
        lines = [d1_line(f"{entity['path']}/{c['id']}") for c in live]
        gone = len(comps) - len(live)
        return ('## Components (D1; open one with `module_guide("<module>/<component>", depth="D2")`)\n'
                + '\n'.join(lines) + (f"\n- … and {gone} obsolete component(s), kept for rollback only" if gone else ''))
    return ''


def _readme_header(path: Path) -> str:
    """The standard header of a README (title + its `| **Rôle** | … |` table), not the whole file."""
    lines = path.read_text(errors='replace').splitlines()
    out, in_table = [], False
    for line in lines[:60]:
        if line.startswith('|'):
            in_table = True
            out.append(line)
        elif in_table:
            break
        elif line.startswith('# ') and not out:
            out.append(line)
            out.append('')
    return '\n'.join(out).strip()


def _component_card(entity: dict) -> str:
    m, c = entity['module'], entity['component']
    rows = [f"# {entity['path']}", '', f"**Role.** {_definition(entity)}", f"**Status.** {c.get('status', 'unknown')}",
            f"**Source.** `{c.get('path', m['root'])}`"]
    if c.get('data'):
        rows.append('**Data.** ' + ', '.join(f'`{d}`' for d in c['data']))
    readme = c.get('readme')
    module_readme = str(Path(m['root']) / 'README.md')
    if readme:
        rows.append(f"**Documentation (D3).** `{readme}`" + (' (the module README)' if readme == module_readme else ''))
    rows.append(f"**Module.** `{m['id']}` — D2: `module_guide(\"{m['id']}\", depth=\"D2\")`.")
    text = '\n'.join(rows)
    if readme and readme != module_readme and Path(readme).is_file():
        header = _readme_header(Path(readme))
        if header:
            text += '\n\n' + header
    return _render(text)


def d2(path: str = ENTITY) -> str:
    entity = resolve(path)
    if entity['kind'] == 'walter':
        body = _render(_walter_file('MANIFEST.md').read_text().strip())
    elif entity['kind'] == 'module':
        m = entity['module']
        if isinstance(m.get('presentation'), dict):
            body = manifest(m['id'])
        else:
            contract = m.get('contract') or {}
            body = f"# {m['id']}\n\n**Role.** {contract.get('purpose', '')}\n\n**Interfaces.** " + \
                   ', '.join(m.get('interfaces') or []) + f"\n\nD3: `{Path(m['root']) / 'README.md'}`"
    else:
        return _component_card(entity)
    children = _children(entity)
    return body + ('\n\n' + children if children else '')


def d3(path: str = ENTITY) -> str:
    entity = resolve(path)
    if entity['kind'] == 'walter':
        return _render(_walter_file('GUIDE.md').read_text())
    if entity['kind'] == 'module':
        m = entity['module']
        text = guide(m['id']) if isinstance(m.get('presentation'), dict) else _clip_file(Path(m['root']) / 'README.md')
        contract = (m.get('contract') or {})
        sources = [f"- Module root: `{m['root']}`", f"- README: `{Path(m['root']) / 'README.md'}`"]
        if m.get('anchors'):
            sources.append(f"- Contract and anchors: `{m['anchors'][0]}`")
        if contract.get('purpose'):
            sources.append(f"- Contract purpose: {contract['purpose']}")
        return text.rstrip() + '\n\n## Sources\n' + '\n'.join(sources)
    c = entity['component']
    readme = Path(c['readme']) if c.get('readme') else None
    card = _component_card(entity)
    if readme and readme.is_file():
        return card + '\n\n---\n\n' + _clip_file(readme)
    return card


def document(path: str = ENTITY, depth: str = 'D2') -> str:
    """`module_guide(path, depth)`: any depth of any entity, directly."""
    depth = (depth or 'D2').upper()
    if depth not in DEPTHS:
        raise ValueError("depth is 'D1', 'D2' or 'D3'")
    return {'D1': d1, 'D2': d2, 'D3': d3}[depth](path)


SOCLE_FORMS = ('s1', 's2')


def socle(form: str = 's2') -> str:
    """The documentation part of an agent's permanent instructions: W.Alter's D1, how to read any depth, and (s2) the
    modules at their D1. Built from the same files as `module_guide`, never a copy."""
    if form not in SOCLE_FORMS:
        raise ValueError('form must be one of ' + ', '.join(SOCLE_FORMS))
    head = ['## W.Alter', _definition(resolve(ENTITY)),
            'Documentation: W.Alter, each module and each component are described at three depths — D1 what it is, '
            'D2 its role, organisation, tools, where to check its live state and its children, D3 its technical detail '
            'and sources. Read any depth directly with `module_guide(path, depth)`, where path is `walter`, a module '
            '(`memory`) or a component (`memory/events`). Go as deep as the task requires; the documentation '
            'describes structure, while `walter_health`, `walter_modules` and `module_index` give the live state.']
    if form == 's1':
        head.append('`module_guide("walter", depth="D2")` lists every module with its path.')
        return '\n'.join(head)
    lines = [d1_line(m['id']) for m in _entries()]
    return '\n'.join(head) + '\n\n### Modules (D1)\n' + '\n'.join(lines)
