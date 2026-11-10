"""Move one module to its place in the vision tree (lot E9, 2026-11-10): plan, apply, verify, rollback.

Moving is not rewriting: the module keeps its code, public names and data; only its folder changes.
  plan      references to the old folder and to its legacy link (code, units, command links, instance
            configuration, harness settings), git state, worktrees, containers mounting it
  apply     backup (catalog, every file and link it will touch) → mv (same filesystem) → compatibility link at
            the old place → command / legacy links repointed → references rewritten → catalog updated →
            systemd reloaded, active units whose unit files were rewritten restarted (others keep running via the compat link)
  verify    catalog and links in place, no live reference left to the old folder, restarted units active
  rollback  the manifest of an apply, undone in reverse order

Files that record history (decisions, plans, evidence, migrations, tests) are reported, never rewritten.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import paths

# Where references live, besides /walter itself ('~/' = service user's home, '@instance' = active instance).
REFERENCE_ROOTS = ('/etc/systemd/system', '~/.config/systemd/user', '/usr/local/bin', '/usr/local/sbin',
                   '/etc/walter', '/etc/logrotate.d', '/etc/cron.d', '/services', '@instance/config',
                   '~/.claude/settings.json', '~/.codex/config.toml', '~/CLAUDE.md', '/opt/dsh/home/cordis.patch.yml',
                   '/opt/dsh/home/config.toml', '/opt/dsh/home/AGENTS.md')
LINK_ROOTS = (('/usr/local/bin', 1), ('/usr/local/sbin', 1), ('/opt', 1), ('/walter', 3), ('~/.hermes', 1),
              ('/etc/systemd/system', 2), ('@instance', 2))
SKIP_DIRS = ('.git', 'venv', '.venv', 'node_modules', '__pycache__', 'site-packages', '.worktrees', '.pytest_cache',
             'state', 'data', 'python', 'dist', 'build', 'npm-cache')
# Reported, never rewritten: history, evidence, applied migrations, test fixtures, generated renders.
KEEP = re.compile(r'(/tests?/|/migrations/|/evidence/|/reports?/|/history/|/archive/|/DECISIONS\.md$|/PLAN\.md$|'
                  r'CHANGELOG|/0[1-5]-[A-Z]+\.md$|\.jsonl$|/modules/catalog\.json$|/modules/registry\.json$|contracts\.generated\.md$)')
MAX_BYTES = 2_000_000
# Path files of the installed environments (site-packages is skipped by the text scan).
PTH_GLOBS = ('/services/python/*/lib/python*/site-packages/*.pth',)


def _expand(value):
    if value.startswith('~/'):
        return Path.home() / value[2:]
    if paths.is_instance_path(value):
        from . import instance
        return Path(str(instance.root())) / value[len(paths.INSTANCE):].lstrip('/')
    return Path(value)


def _on(fs, p):
    return Path(fs) / str(p).lstrip('/')


def _boundary(prefix):
    return re.compile(re.escape(prefix) + r'(?![\w.-])')


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _run(*cmd, cwd=None, check=False):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=300)
    except FileNotFoundError:                      # tool absent on this host (crontab, docker): nothing to report
        r = subprocess.CompletedProcess(cmd, 127, '', f'{cmd[0]}: not installed')
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr.strip()[:300]}")
    return r


class Move:
    def __init__(self, module, to=None, *, catalog=None, fs='/', root=None, reference_roots=None, link_roots=None):
        self.fs, self.catalog_file = fs, Path(catalog or paths.CATALOG)
        self.item = paths.entry(module, self.catalog_file)
        self.id = self.item['id']
        self.root = Path(str(root or paths.walter_root()))
        self.old = self.root / str(paths.relative(self.item['target']))
        dest = to or self.item.get('vision_target')
        if not dest:
            raise ValueError(f'{self.id}: no destination (vision_target)')
        self.new = self.root / str(paths.relative(dest))
        self.legacy = Path(self.item['legacy']) if self.item.get('legacy') else None
        self.reference_roots = reference_roots or REFERENCE_ROOTS
        self.link_roots = link_roots or LINK_ROOTS
        # (prefix, replacement): the folder, its legacy link, and the legacy links of modules nested inside it
        self.mapping = [(str(self.old), str(self.new))] + ([(str(self.legacy), str(self.new))] if self.legacy else [])
        for e in self._entries_under():
            here = str(self.root / str(paths.relative(e['target'])))
            if e.get('legacy') and e['legacy'] != self.item.get('legacy') and here != str(self.old):
                self.mapping.append((e['legacy'], str(self.new) + here[len(str(self.old)):]))
        self.prefixes = [p for p, _ in self.mapping]

    # ---- inventory -----------------------------------------------------------------------------------------
    def _rewrite(self, text):
        for prefix, replacement in self.mapping:
            text = _boundary(prefix).sub(replacement, text)
        return text

    def references(self, prefixes=None):
        roots = [str(_on(self.fs, self.root))] + [str(_on(self.fs, _expand(r))) for r in self.reference_roots]
        roots = [r for r in roots if os.path.exists(r)]
        cmd = ['grep', '-rIlsF'] + [f'--exclude-dir={d}' for d in SKIP_DIRS]
        prefixes = prefixes or self.prefixes
        for p in prefixes:
            cmd += ['-e', p]
        found = _run(*cmd, *roots).stdout.split('\n') if roots else []
        import glob
        for pattern in PTH_GLOBS:
            found += glob.glob(str(_on(self.fs, pattern)))
        rewrite, keep = [], []
        for f in sorted({f for f in found if f}):
            p = Path(f)
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                continue
            text = p.read_text(errors='replace')
            if not any(_boundary(x).search(text) for x in prefixes):   # only a longer name shares the prefix
                continue
            (keep if KEEP.search(f) else rewrite).append(f)
        return rewrite, keep

    def links(self):
        out = []
        for base, depth in self.link_roots:
            top = _on(self.fs, _expand(base))
            if not top.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(top):
                level = len(Path(dirpath).relative_to(top).parts)
                dirnames[:] = [d for d in dirnames if level + 1 < depth and d not in SKIP_DIRS
                               and not os.path.islink(os.path.join(dirpath, d))]
                for name in filenames + [d for d in os.listdir(dirpath) if os.path.islink(os.path.join(dirpath, d))]:
                    p = os.path.join(dirpath, name)
                    if not os.path.islink(p):
                        continue
                    raw = os.readlink(p)
                    after = self._rewrite(raw)
                    if after != raw and p != str(_on(self.fs, self.old)):
                        out.append({'path': p, 'before': raw, 'after': after})
        return sorted({l['path']: l for l in out}.values(), key=lambda l: l['path'])

    def repositories(self):
        base = _on(self.fs, self.old)
        repos = []
        for dirpath, dirnames, _ in os.walk(base):
            if '.git' in os.listdir(dirpath) and os.path.isdir(os.path.join(dirpath, '.git')):
                repos.append(dirpath)
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d))
                           and len(Path(dirpath, d).relative_to(base).parts) <= 3]
        return repos

    def worktrees(self, repo):
        r = _run('git', '-C', repo, 'worktree', 'list', '--porcelain')
        return [l[9:] for l in r.stdout.splitlines() if l.startswith('worktree ') and l[9:] != repo]

    def services(self):
        """Services the module's contract declares (they run its code)."""
        try:
            contract = json.loads((_on(self.fs, self.old) / self.item['manifest']).read_text())
        except (OSError, KeyError, ValueError):
            return []
        return [(s if s.endswith(('.service', '.timer')) else s + '.service', False)
                for s in contract.get('services') or []]

    def units(self, files):
        names = list(self.services()) if _on(self.fs, self.old).is_dir() else []
        return sorted(set(names) | set(self.file_units(files)))

    def file_units(self, files):
        names = []
        for f in files:
            if '/systemd/' in f and f.endswith(('.service', '.timer', '.conf')):
                name = Path(f).name if f.endswith(('.service', '.timer')) else Path(f).parent.name.removesuffix('.d')
                user = '/.config/systemd/user' in f
                if f.startswith(str(_on(self.fs, '/etc/systemd'))) or user:
                    names.append((name, user))
        return sorted(set(names))

    def containers(self):
        r = _run('docker', 'ps', '-q')
        ids = r.stdout.split()
        if r.returncode or not ids:
            return []
        r = _run('docker', 'inspect', '--format', '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}', *ids)
        return [l.strip() for l in r.stdout.splitlines() if any(p in l for p in self.prefixes)]

    def plan(self):
        problems = []
        old, new = _on(self.fs, self.old), _on(self.fs, self.new)
        if not old.is_dir() or old.is_symlink():
            problems.append(f'{self.old} is not the module folder (already moved?)')
        if new.exists() or new.is_symlink():
            problems.append(f'{self.new} already exists')
        if old.is_dir() and new.parent.exists() and old.stat().st_dev != new.parent.stat().st_dev:
            problems.append('destination on another filesystem (a move would copy)')
        rewrite, keep = self.references()
        dirty = []
        for f in rewrite:
            r = _run('git', 'status', '--porcelain', '--', Path(f).name, cwd=str(Path(f).parent))
            if r.returncode == 0 and r.stdout.strip():
                dirty.append(f)
        repos = self.repositories() if old.is_dir() else []
        cron = _run('crontab', '-l').stdout
        return {'module': self.id, 'old': str(self.old), 'new': str(self.new),
                'legacy': str(self.legacy) if self.legacy else None,
                'catalog_entries': [e['id'] for e in self._entries_under()],
                'rewrite': [f for f in rewrite if f not in dirty], 'rewrite_dirty': dirty, 'report_only': keep,
                'links': self.links(), 'units': [{'unit': u, 'user': user} for u, user in self.units(rewrite)],
                # restarted after the move: only units whose own files are rewritten (the others keep running
                # through the compatibility link; a browser or engine is never cut for a folder move)
                'restart': [{'unit': u, 'user': user} for u, user in self.file_units(rewrite)],
                'repositories': {r: {'dirty': bool(_run('git', '-C', r, 'status', '--porcelain').stdout.strip()),
                                     'worktrees': self.worktrees(r)} for r in repos},
                'containers': self.containers(),
                'crontab': [l for l in cron.splitlines() if any(p in l for p in self.prefixes)],
                'real_venvs': [str(p.parent) for p in old.glob('**/pyvenv.cfg') if '.worktrees' not in p.parts
                               and not any(x.is_symlink() for x in p.parents if str(x).startswith(str(old)))]
                if old.is_dir() else [],
                'problems': problems, 'ok': not problems}

    def _entries_under(self):
        data = json.loads(self.catalog_file.read_text())
        old = str(self.old)
        return [e for e in data['modules']
                if str(self.root / str(paths.relative(e['target']))) == old
                or str(self.root / str(paths.relative(e['target']))).startswith(old + '/')]

    # ---- apply ---------------------------------------------------------------------------------------------
    def apply(self, backup_dir, *, systemd=True, allow_dirty=False):
        plan = self.plan()
        if not plan['ok']:
            raise RuntimeError('; '.join(plan['problems']))
        if plan['rewrite_dirty'] and not allow_dirty:
            raise RuntimeError('files with uncommitted changes to rewrite: ' + ', '.join(plan['rewrite_dirty']))
        bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        os.chmod(bdir, 0o700)
        shutil.copy2(self.catalog_file, bdir / 'catalog.json')
        old, new = _on(self.fs, self.old), _on(self.fs, self.new)

        def after(f):                                 # where a file lives once the folder has moved
            return str(new) + f[len(str(old)):] if f == str(old) or f.startswith(str(old) + '/') else f

        rewritten = []
        for f in plan['rewrite'] + (plan['rewrite_dirty'] if allow_dirty else []):
            copy = bdir / 'files' / f.lstrip('/')
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, copy)
            rewritten.append({'before': f, 'after': after(f), 'sha_before': _sha(f), 'copy': str(copy)})
        manifest = {'module': self.id, 'old': str(self.old), 'new': str(self.new), 'fs': self.fs,
                    'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'catalog': str(self.catalog_file),
                    'rewritten': rewritten, 'links': plan['links'], 'units': plan['restart'],
                    'worktrees': {r: plan['repositories'][r]['worktrees'] for r in plan['repositories']},
                    'mapping': self.mapping,
                    'step': 'backed-up'}
        mpath = bdir / 'manifest.json'
        mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))

        new.parent.mkdir(parents=True, exist_ok=True)
        os.rename(old, new)
        os.symlink(str(self.new), old)              # compatibility: the old place still answers
        manifest['step'] = 'moved'
        mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))

        for link in plan['links']:
            p = after(link['path'])
            tmp = p + '.e9tmp'
            os.symlink(link['after'], tmp)
            os.replace(tmp, p)
        for r in rewritten:
            p = Path(r['after'])
            p.write_text(self._rewrite(p.read_text(errors='replace')))
            r['sha_after'] = _sha(p)
        for repo, trees in manifest['worktrees'].items():
            moved = [after(t) for t in trees]
            if moved:
                _run('git', '-C', after(repo), 'worktree', 'repair', *moved)
        self._update_catalog()
        self._render_registry()
        manifest['step'] = 'applied'
        mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
        if systemd:
            manifest['restarted'] = _systemd(plan['restart'])
            mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
        return manifest

    def _update_catalog(self):
        data = json.loads(self.catalog_file.read_text())
        old, new = str(self.old), str(self.new)
        for e in data['modules']:
            here = str(self.root / str(paths.relative(e['target'])))
            if here == old or here.startswith(old + '/'):
                e['target'] = str(Path(new + here[len(old):]).relative_to(self.root))
                if here == old and e['id'] == self.id:
                    links = [l for l in e.get('compat_links') or [] if l != old]
                    e['compat_links'] = links + [old]
        self.catalog_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

    def _render_registry(self):
        """The generated registry and its markdown follow the catalog (real catalog only)."""
        if self.catalog_file != paths.CATALOG:
            return
        core = paths.CATALOG.parent.parent
        for fmt, out in (('json', core / 'modules' / 'registry.json'), ('markdown', core / 'docs' / 'contracts.generated.md')):
            r = _run('walter', 'contracts', 'render', '--format', fmt)
            if r.returncode == 0 and r.stdout.strip():
                out.write_text(r.stdout)

    # ---- verify / rollback ---------------------------------------------------------------------------------
    @classmethod
    def from_manifest(cls, m, **kw):
        """The move an apply recorded (the catalog already points at the new place)."""
        self = cls.__new__(cls)
        self.fs, self.catalog_file = m.get('fs', '/'), Path(m['catalog'])
        self.item = paths.entry(m['module'], self.catalog_file)
        self.id, self.root = self.item['id'], Path(str(kw.get('root') or paths.walter_root()))
        self.old, self.new = Path(m['old']), Path(m['new'])
        self.legacy = Path(self.item['legacy']) if self.item.get('legacy') else None
        self.reference_roots = kw.get('reference_roots') or REFERENCE_ROOTS
        self.link_roots = kw.get('link_roots') or LINK_ROOTS
        self.mapping = [tuple(x) for x in m['mapping']]
        self.prefixes = [p for p, _ in self.mapping]
        return self

    def verify(self, manifest=None):
        lay = {r['id']: r for r in paths.layout(catalog=self.catalog_file, filesystem=self.fs)['modules']}
        row = lay[self.id]
        rewrite, _ = self.references(self.prefixes)
        units = []
        for u in (manifest or {}).get('restarted', []):
            state = _run(*(['systemctl', '--user'] if u['user'] else ['systemctl']), 'is-active', u['unit']).stdout.strip()
            units.append({**u, 'state': state})
        checks = {'moved': row['moved'] and row['root'] == str(self.new),
                  'compat_link': (row.get('compat_links') or {}).get(str(self.old)) == 'compat-link',
                  'legacy_link': row['legacy_link'] in (None, 'compat-link', 'absent'),
                  'references_left': rewrite, 'units': units}
        checks['ok'] = (checks['moved'] and checks['compat_link'] and checks['legacy_link'] and not rewrite
                        and all(u['state'] == 'active' for u in units))
        return checks


def _systemd(units):
    _run('systemctl', 'daemon-reload')
    _run('systemctl', '--user', 'daemon-reload')
    restarted = []
    for u in units:
        if not u['unit'].endswith('.service'):
            continue
        base = ['systemctl', '--user'] if u['user'] else ['systemctl']
        if _run(*base, 'is-active', u['unit']).stdout.strip() == 'active':
            _run(*base, 'restart', u['unit'])
            restarted.append(u)
    return restarted


def rollback(backup_dir, *, systemd=True):
    bdir = Path(backup_dir)
    m = json.loads((bdir / 'manifest.json').read_text())
    fs = m.get('fs', '/')
    old, new = _on(fs, m['old']), _on(fs, m['new'])
    for r in m['rewritten']:                         # content back first, while the files are at their new place
        dest = Path(r['after'] if new.is_dir() and not new.is_symlink() else r['before'])
        if dest.exists():
            shutil.copy2(r['copy'], dest)
    for link in m['links']:
        p = link['path']
        if os.path.islink(p) or not os.path.exists(p):
            tmp = p + '.e9tmp'
            os.symlink(link['before'], tmp)
            os.replace(tmp, p)
    if new.is_dir() and not new.is_symlink() and old.is_symlink():
        old.unlink()
        os.rename(new, old)
        try:
            new.parent.rmdir()                       # a family folder created for this move, if now empty
        except OSError:
            pass
    for repo, trees in m.get('worktrees', {}).items():
        if trees:
            _run('git', '-C', repo, 'worktree', 'repair', *trees)
    shutil.copy2(bdir / 'catalog.json', m['catalog'])
    if Path(m['catalog']) == paths.CATALOG:
        Move._render_registry(type('M', (), {'catalog_file': paths.CATALOG})())
    if systemd:
        _systemd(m['units'])
    m['step'] = 'rolled-back'
    (bdir / 'manifest.json').write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return {'module': m['module'], 'back_at': m['old'], 'ok': old.is_dir() and not old.is_symlink()}


# ---- installed Python environments → /services/python/<name> (arbitrage du 09/11) ------------------------------
ENV_TEXT = ('pyvenv.cfg',)


def _env_files(env):
    """Files of an environment that carry its own path: launchers and activation scripts, path files, install records."""
    env = Path(env)
    out = [env / n for n in ENV_TEXT if (env / n).is_file()]
    for p in (env / 'bin').iterdir() if (env / 'bin').is_dir() else []:
        if p.is_file() and not p.is_symlink() and p.stat().st_size < 1_000_000:
            head = p.read_bytes()[:4096]
            if b'\0' not in head:
                out.append(p)
    for site in env.glob('lib/python*/site-packages'):
        out += [p for p in site.glob('*.pth') if p.is_file()]
        out += [p for p in site.glob('*.dist-info/direct_url.json') if p.is_file()]
        out += [p for p in site.glob('*.dist-info/RECORD') if p.is_file()]
    return out


def _env_prefixes(src, catalog=None):
    """The environment's path and the same path seen through each module's legacy link."""
    src = str(src)
    out = [src]
    for e in json.loads(Path(catalog or paths.CATALOG).read_text())['modules']:
        root = str(paths.walter_root() / str(paths.relative(e['target'])))
        if e.get('legacy') and (src == root or src.startswith(root + '/')):
            out.append(e['legacy'] + src[len(root):])
    return sorted(set(out), key=len, reverse=True)


def env_plan(src, dest):
    src, dest = Path(src), Path(dest)
    problems = []
    if not (src / 'pyvenv.cfg').is_file() or src.is_symlink():
        problems.append(f'{src} is not an installed environment (or already moved)')
    if dest.exists() or dest.is_symlink():
        problems.append(f'{dest} already exists')
    elif dest.parent.exists() and src.exists() and src.stat().st_dev != dest.parent.stat().st_dev:
        problems.append('destination on another filesystem (a move would copy)')
    prefixes = _env_prefixes(src)
    files = [str(p) for p in _env_files(src) if not src.is_symlink() and any(_boundary(x).search(
        p.read_text(errors='replace')) for x in prefixes)] if not problems else []
    top = _run('git', '-C', str(src.parent), 'rev-parse', '--show-toplevel').stdout.strip()
    return {'env': str(src), 'dest': str(dest), 'prefixes': prefixes, 'rewrite': files, 'repository': top or None,
            'problems': problems, 'ok': not problems}


def env_apply(src, dest, backup_dir):
    plan = env_plan(src, dest)
    if not plan['ok']:
        raise RuntimeError('; '.join(plan['problems']))
    src, dest, bdir = Path(src), Path(dest), Path(backup_dir)
    bdir.mkdir(parents=True, exist_ok=True)
    os.chmod(bdir, 0o700)
    rewritten = []
    for f in plan['rewrite']:
        copy = bdir / 'files' / f.lstrip('/')
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, copy)
        rewritten.append({'before': f, 'after': str(dest) + f[len(str(src)):], 'copy': str(copy)})
    m = {'kind': 'env', 'env': str(src), 'dest': str(dest), 'rewritten': rewritten, 'prefixes': plan['prefixes'],
         'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'step': 'backed-up'}
    (bdir / 'manifest.json').write_text(json.dumps(m, indent=1, ensure_ascii=False))
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dest)
    os.symlink(str(dest), src)                       # the module keeps its `venv` name, now a pointer
    for r in rewritten:
        p = Path(r['after'])
        text = p.read_text(errors='replace')
        for x in plan['prefixes']:
            text = _boundary(x).sub(str(dest), text)
        p.write_text(text)
    ignored = None
    if plan['repository']:
        rel = str(src.relative_to(plan['repository']))
        if _run('git', '-C', plan['repository'], 'check-ignore', '-q', rel).returncode:
            with open(Path(plan['repository']) / '.gitignore', 'a') as f:
                f.write(f'/{rel}\n')
            ignored = rel
    m.update(step='applied', gitignore_added=ignored)
    (bdir / 'manifest.json').write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return m


def env_verify(m):
    dest = Path(m['dest'])
    py = dest / 'bin' / 'python3'
    r = _run(str(Path(m['env']) / 'bin' / 'python3'), '-c', 'import sys,json;print(json.dumps([sys.prefix,sys.path]))')
    left = [str(p) for p in _env_files(dest) if any(_boundary(x).search(p.read_text(errors='replace'))
                                                    for x in m['prefixes'] if x != str(dest))]
    return {'env': m['env'], 'link': Path(m['env']).is_symlink() and Path(m['env']).resolve() == dest.resolve(),
            'python': r.returncode == 0 and py.exists(), 'old_paths_left': left,
            'ok': r.returncode == 0 and not left and Path(m['env']).is_symlink()}


def env_rollback(backup_dir):
    bdir = Path(backup_dir)
    m = json.loads((bdir / 'manifest.json').read_text())
    src, dest = Path(m['env']), Path(m['dest'])
    if src.is_symlink() and dest.is_dir():
        src.unlink()
        os.rename(dest, src)
    for r in m['rewritten']:
        shutil.copy2(r['copy'], r['before'])
    if m.get('gitignore_added'):                     # the ignore line the apply added, and only it
        top = _run('git', '-C', str(src.parent), 'rev-parse', '--show-toplevel').stdout.strip()
        gi = Path(top) / '.gitignore'
        lines = gi.read_text().splitlines(keepends=True)
        line = f"/{m['gitignore_added']}\n"
        if line in lines:
            lines.reverse(); lines.remove(line); lines.reverse()
            gi.write_text(''.join(lines))
    m['step'] = 'rolled-back'
    (bdir / 'manifest.json').write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return {'env': str(src), 'ok': src.is_dir() and not src.is_symlink()}
