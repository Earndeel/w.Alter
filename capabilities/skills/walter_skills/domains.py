"""Curator-published discovery index. Overview → domain entries → explicit skill read.

Only metadata is exposed here; procedure bodies and supporting files stay behind skill_read.
The local snapshot is derived, atomically replaced, and usable without Postgres.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path

from . import registry, store


def _order(e: dict) -> tuple:
    """Entry skills first (they route), then workflows, then procedures."""
    return ({'entry': 0, 'workflow': 1}.get(e['kind'], 2), e['name'])


def _snapshot(root: Path | None = None) -> Path:
    return (root or store.ROOT) / '.cache' / 'library-index.json'


def build(top: int = 5) -> list[dict]:
    """Publish active entries after curation; `top` is retained for old callers."""
    cards = registry.cards()
    groups = defaultdict(list)
    for s in store.iter_skills():
        fm = store.frontmatter(s.body[:8000])
        card = cards.get(s.name, {})
        kind = s.meta.get('kind') or fm.get('type') or card.get('kind') or 'procedure'
        requires = s.meta.get('requires') or []
        groups[s.domain or 'uncategorized'].append({
            'name': s.name, 'kind': kind,
            'purpose': ' '.join((s.description or card.get('summary') or s.name).split())[:240],
            'requires': list(requires) if isinstance(requires, list) else [],
        })
    reserve = defaultdict(list)  # archived with reserve: true (not merged): listed, read restores them
    for s in store.iter_skills(include_archived=True):
        if s.state == 'archived' and s.meta.get('reserve') and not s.meta.get('absorbed_into'):
            card = cards.get(s.name, {})
            reserve[s.meta.get('domain') or 'uncategorized'].append({
                'name': s.name, 'kind': 'reserve',
                'purpose': ' '.join((s.description or card.get('summary') or s.name).split())[:240]})
    out = []
    for domain in sorted(set(groups) | set(reserve)):
        entries = sorted(groups.get(domain, []), key=_order)
        res = sorted(reserve.get(domain, []), key=lambda e: e['name'])
        out.append({'domain': domain, 'count': len(entries),
                    'workflows': sum(e['kind'] == 'workflow' for e in entries), 'entries': entries,
                    'reserve': len(res), 'reserve_entries': res})
    # Build the whole document before publishing. Readers never observe half an index.
    path = _snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='library-index-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(out, f, ensure_ascii=False, sort_keys=True)
            f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    registry.set_state('domain_map', out)
    return out


def _load(root: Path | None = None) -> list[dict]:
    # Use the published local snapshot on the runtime path: no DB/LLM/embedding work per message.
    try:
        return json.loads(_snapshot(root).read_text())
    except (OSError, ValueError):
        if root is not None:
            raise RuntimeError('Discovery index unavailable; use search/read.')
        m = registry.get_state('domain_map')
        return m if m and all('entries' in d for d in m) else build()


def index(domain: str = '', offset: int = 0, limit: int = 20, *, root: Path | None = None) -> dict:
    """Empty domain lists domains; a selected domain returns a bounded page, workflows first."""
    m = _load(root)
    if not domain:
        return {'domains': [{k: d.get(k, 0) for k in ('domain', 'count', 'workflows', 'reserve')} for d in m],
                'total': sum(d['count'] for d in m), 'reserve': sum(d.get('reserve', 0) for d in m)}
    mine = [d for d in m if d['domain'] == domain or d['domain'].startswith(domain + '/')]
    entries = sorted((e | {'domain': d['domain']} for d in mine for e in d['entries']), key=_order)
    # The reserve comes after the active entries: skill_read on one of them puts it back in service.
    entries += sorted((e | {'domain': d['domain']} for d in mine for e in d.get('reserve_entries', [])),
                      key=lambda e: e['name'])
    offset, limit = max(0, offset), max(1, min(limit, 20))
    end = offset + limit
    return {'domain': domain, 'entries': entries[offset:end], 'total': len(entries),
            'offset': offset, 'next_offset': end if end < len(entries) else None}


def manifest(root: Path | None = None) -> str:
    return ((root or Path(__file__).resolve().parent.parent) / 'manifest' / 'GUIDE.md').read_text()


def render(search_tool: str) -> str:
    hermes = search_tool.startswith('walter_')
    index_tool = 'walter_skills_index' if hermes else 'skills_index'
    manifest_tool = 'walter_skills_manifest' if hermes else 'skills_manifest'
    data = index()
    header = ("W.Alter Skills — bibliothèque de procédures et workflows, partagée entre les agents.\n"
              f"{manifest_tool} explique le module ; {index_tool}(domain=…) indique à quoi sert chaque entrée. "
              f"{search_tool}(query=…) cherche par intention. Lis ensuite le skill choisi et seulement ses références utiles.\n"
              "Index compact des domaines (total / workflows ; réserve = skills dormants, toujours trouvables, "
              "réactivés dès qu'on les lit) :\n")
    return header + '\n'.join(_line(d) for d in data['domains'])


def _line(d: dict) -> str:
    return f"- {d['domain']} : {d['count']} / {d['workflows']}" + (f" · réserve {d['reserve']}" if d.get('reserve') else "")


def domain_map() -> str:
    """Live part of the module's level-1 manifest: the compact domain map (manifest/MANIFEST.md says how to use it)."""
    data = index()
    return ("Domaines (total / workflows · réserve) :\n" + '\n'.join(_line(d) for d in data['domains']))


def brief_document(search_tool: str = 'skills_search') -> dict:
    """Level 0 of the module in the shared v1 note envelope consumed by walter-context (walter present)."""
    import hashlib
    hermes = search_tool.startswith('walter_')
    content = '### W.Alter Skills — procédures et workflows partagés entre les agents\n' + render(search_tool).split('\n', 1)[1]
    tools = ([search_tool, 'walter_skills_index', 'walter_skill_read'] if hermes
             else [search_tool, 'skills_index', 'skill_read'])
    return {'schema_version': 1, 'note_version': 1, 'id': 'walter-skills.brief', 'module': 'skills',
            'format': 'text/markdown', 'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest(),
            'chars': len(content), 'required_tools': tools, 'placement': 'stable_capabilities',
            'refresh': 'next_owner_message', 'source': {'command': 'walter-skills', 'args': ['brief', '--json']}}
