"""Deploy freshness: does every long-running Walter service run the code that is on disk? (SOCLE A8, 2026-11-11)

Incident of 2026-11-11: shared library code was fixed on disk at 06:17 UTC, but three services started the day
before kept the old code in memory; 409 model calls failed over four hours while every supervisor said ok.

For each long-running service declared in the registry (module contracts -> ``services``; timers are excluded:
each run starts fresh), this compares the unit's ``ActiveEnterTimestamp`` with the newest modification time of the
code the process loads:

  python   the entry (ExecStart resolved through symlinks: a script, ``-m module``, ``-m uvicorn pkg.mod:app``, or a
           shell wrapper that ends in one of those) and every first-party module it imports, statically and
           transitively (ast; only files under the Walter root or a declared code root are followed, never
           site-packages), so a service is not flagged for a library it never imports;
  node     the entry file when it lives under Walter, plus the roots declared by the contracts;
  declared ``service_code`` in any module contract: ``{"<unit>": {"code_roots": [...], "code_files": [...]}}`` — a
           module declares which of its code a unit loads (dsh-web: engine plugins, Engine API, context port,
           rendered composition). Roots are scanned for .py .mjs .js .ts .cjs, skipping tests, docs, state, caches,
           venvs and generated data; ``code_files`` count whatever their extension.

Read-only except ``restart`` (the guardian's allowed repair), which re-checks staleness, never restarts the engine or
its Telegram door while an engine turn is in flight, restarts a unit at most once per hour, and checks again after.
Unit facts are injectable (tests need no systemd).
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CODE_EXT = {'.py', '.mjs', '.js', '.ts', '.cjs'}
EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'tests', 'test', 'bench', 'docs', 'reports',
                'state', '.cache', 'cache', 'data', 'generated', 'fixtures', 'evidence', '.pytest_cache', 'dist',
                'build', 'manifest', 'contracts'}
TOLERANCE_S = 2.0
RESTART_EVERY_S = 3600              # one restart per service per hour
TURN_MAX_S = 1800                   # an open engine run older than this is not a turn in flight
ENGINE_UNITS = {'dsh-web', 'walter-telegram'}   # interrupting them drops a running owner turn
PYTHON = re.compile(r'(^|/)(python3?(\.\d+)?|walter-python)$')


def _unit(name):
    return name[:-len('.service')] if name.endswith('.service') else name


def _now():
    return time.time()


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='seconds') if ts else None


# ---- unit facts ---------------------------------------------------------------------------------------------------

def unit_facts(unit):
    """{active, started_at (unix), argv, workdir, env} of a systemd unit, read with systemctl show."""
    props = ('ActiveState', 'ActiveEnterTimestamp', 'ExecStart', 'WorkingDirectory', 'Environment', 'LoadState')
    try:
        r = subprocess.run(['systemctl', 'show', '--timestamp=unix', unit + '.service',
                            *[f'-p{p}' for p in props]], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return {'error': 'systemctl_unavailable'}
    p = dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)
    started = None
    m = re.match(r'@(\d+)', p.get('ActiveEnterTimestamp', ''))
    if m:
        started = float(m.group(1))
    argv = re.search(r'argv\[\]=([^;]*)', p.get('ExecStart', ''))
    env = {}
    for item in re.findall(r'(?:"[^"]*"|\S)+', p.get('Environment', '')):
        k, _, v = item.strip('"').partition('=')
        if k:
            env[k] = v
    return {'loaded': p.get('LoadState') == 'loaded', 'active': p.get('ActiveState') == 'active',
            'started_at': started, 'argv': argv.group(1).split() if argv else [],
            'workdir': p.get('WorkingDirectory') or '/', 'env': env}


_SYS_PATH = {}


def interpreter_path(interp, workdir='/'):
    """sys.path of an interpreter (site .pth files included); read once per interpreter. Read-only."""
    if interp not in _SYS_PATH:
        try:
            r = subprocess.run([interp, '-c', 'import json,sys;print(json.dumps(sys.path[1:]))'], capture_output=True,
                               text=True, timeout=20, cwd=workdir if os.path.isdir(workdir) else '/')
            _SYS_PATH[interp] = json.loads(r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            _SYS_PATH[interp] = []
    return _SYS_PATH[interp]


# ---- static import graph ---------------------------------------------------------------------------------------

def _path_expr(node, file):
    """Evaluate the few path expressions modules use to extend their import path (constants, __file__,
    Path(...).resolve().parent / 'x', str(), os.path.dirname/join/abspath/realpath). None when not static."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id == '__file__':
        return str(file)
    if isinstance(node, ast.Attribute):
        base = _path_expr(node.value, file)
        if base is None:
            return None
        return os.path.dirname(base.rstrip('/')) if node.attr == 'parent' else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        a, b = _path_expr(node.left, file), _path_expr(node.right, file)
        return os.path.join(a, b) if a is not None and b is not None else None
    if isinstance(node, ast.Call):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ''
        args = [_path_expr(a, file) for a in node.args]
        if name in ('Path', 'PurePath', 'PosixPath', 'str', 'fspath') and len(args) == 1:
            return args[0]
        if name in ('resolve', 'absolute', 'expanduser') and isinstance(f, ast.Attribute):
            base = _path_expr(f.value, file)
            return os.path.realpath(base) if base is not None and name == 'resolve' else base
        if name in ('dirname', 'abspath', 'realpath') and len(args) == 1 and args[0] is not None:
            return {'dirname': os.path.dirname, 'abspath': os.path.abspath, 'realpath': os.path.realpath}[name](args[0])
        if name == 'join' and args and all(a is not None for a in args):
            return os.path.join(*args)
    return None


class Graph:
    """First-party import closure of a Python entry. ``allowed``: roots whose files are followed."""

    def __init__(self, search, allowed):
        self.search = [os.path.realpath(s) for s in search if s]
        self.allowed = [os.path.realpath(a) for a in allowed]
        self.files, self._pkg, self._mod = set(), {}, {}

    def _ok(self, path):
        real = os.path.realpath(path)
        if any(part in EXCLUDE_DIRS - {'contracts', 'manifest'} for part in Path(real).parts):
            return False
        return any(real == a or real.startswith(a.rstrip('/') + '/') for a in self.allowed)

    def _package_dirs(self, init, default):
        """__path__ of a package: its directory, or what its __init__ assigns statically (walter_router does)."""
        try:
            tree = ast.parse(Path(init).read_text())
        except (OSError, SyntaxError, ValueError):
            return [default]
        for node in tree.body:
            if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__path__' for t in node.targets)
                    and isinstance(node.value, (ast.List, ast.Tuple))):
                dirs = [_path_expr(e, init) for e in node.value.elts]
                if dirs and all(dirs):
                    return [os.path.realpath(d) for d in dirs]
        return [default]

    def resolve(self, name):
        """Files executed by importing ``name`` (every package __init__ on the way), [] if not first-party."""
        if name in self._mod:
            return self._mod[name]
        parts, files, dirs = name.split('.'), [], None
        for i, part in enumerate(parts):
            prefix = '.'.join(parts[:i + 1])
            found = None
            for d in (self.search if dirs is None else dirs):
                pkg, mod = os.path.join(d, part, '__init__.py'), os.path.join(d, part + '.py')
                if os.path.isfile(pkg):
                    found = ('pkg', pkg, os.path.join(d, part))
                    break
                if os.path.isfile(mod):
                    found = ('mod', mod, None)
                    break
                if os.path.isdir(os.path.join(d, part)) and i < len(parts) - 1:
                    found = ('ns', None, os.path.join(d, part))   # namespace package
                    break
            if not found or (found[1] and not self._ok(found[1])):
                self._mod[name] = files if i else []
                return self._mod[name]
            if found[1]:
                files.append(found[1])
            if found[0] == 'mod':
                break
            dirs = self._pkg.setdefault(prefix, self._package_dirs(found[1], found[2]) if found[1] else [found[2]])
        self._mod[name] = files
        return files

    def visit(self, file, package=''):
        file = os.path.realpath(file)
        if file in self.files:
            return
        self.files.add(file)
        try:
            tree = ast.parse(Path(file).read_text(), filename=file)
        except (OSError, SyntaxError, ValueError):
            return
        here = package
        for node in ast.walk(tree):   # path extensions first: they apply to the imports of this file
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('insert', 'append') and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == 'path' and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == 'sys' and node.args):
                p = _path_expr(node.args[-1], file)
                if p and os.path.isdir(p) and os.path.realpath(p) not in self.search:
                    self.search.insert(0, os.path.realpath(p))
        targets = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = here.split('.') if here else []
                    base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
                    mod = '.'.join(base + ([node.module] if node.module else []))
                else:
                    mod = node.module or ''
                if mod:
                    targets.append(mod)
                targets += [f'{mod}.{n.name}' if mod else n.name for n in node.names if n.name != '*']
            elif (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                  and isinstance(node.args[0].value, str)
                  and ((isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module')
                       or (isinstance(node.func, ast.Name) and node.func.id in ('import_module', '__import__')))):
                targets.append(node.args[0].value)
        for t in targets:
            for f in self.resolve(t):
                self.visit(f, self._package_of(t, f))

    def _package_of(self, name, file):
        parts = name.split('.')
        # the module's own package: the prefix whose resolution ends with this file
        for i in range(len(parts), 0, -1):
            files = self.resolve('.'.join(parts[:i]))
            if files and files[-1] == file:
                return '.'.join(parts[:i]) if file.endswith('__init__.py') else '.'.join(parts[:i - 1])
        return ''


def python_entry(argv, workdir, env, interp_path=interpreter_path):
    """(interpreter, entry file or None, entry module or None, extra search dirs, wrapper files)."""
    exe = os.path.realpath(argv[0]) if argv else ''
    wrappers, search, interp = [], [], None
    if PYTHON.search(argv[0] if argv else '') or PYTHON.search(exe):
        interp, args = argv[0], argv[1:]
    else:
        try:
            with open(exe, 'rb') as fh:
                head = fh.read(262144)
        except OSError:
            return None
        if not head.startswith(b'#!'):
            return None   # a binary (rclone, docker, ssh): no Walter code
        text = head.decode('utf-8', 'replace')
        first = text.splitlines()[0] if text else ''
        if first.startswith('#!') and 'python' in first:
            return (first[2:].split()[-1] if 'env' in first else first[2:].split()[0]), exe, None, [os.path.dirname(exe)], []
        if not (first.startswith('#!') and re.search(r'\b(ba)?sh\b', first)):
            return None
        # A shell wrapper ending in a Python process: its `cd`/PYTHONPATH targets and `-m module` / file.py.
        wrappers.append(exe)
        mods = re.findall(r'(?:walter-python|python3?)\s+(?:-\S+\s+)*-m\s+([\w.]+)(?:\s+([\w.]+:\w+))?', text)
        files = re.findall(r'(?:walter-python|python3?)\s+(\S+\.py)\b', text)
        if not mods and not files:
            return None
        interp = 'walter-python' if 'walter-python' in text else 'python3'
        here = os.path.dirname(exe)
        search += [d for d in re.findall(r'\bcd\s+"?(/[^\s"&;]+)', text)] + [here, os.path.dirname(here)]
        if mods:
            m, app = mods[0]
            return interp, None, (app.split(':')[0] if m in ('uvicorn', 'gunicorn', 'hypercorn') and app else m), search, wrappers
        return interp, os.path.join(workdir, files[0]), None, search, wrappers
    module, file, i = None, None, 0
    while i < len(args):
        a = args[i]
        if a == '-m' and i + 1 < len(args):
            module = args[i + 1]
            if module in ('uvicorn', 'gunicorn', 'hypercorn'):
                app = next((x for x in args[i + 2:] if not x.startswith('-') and ':' in x), None)
                module = app.split(':')[0] if app else module
            break
        if a.startswith('-'):
            i += 2 if a in ('-W', '-X') else 1
            continue
        file = a if os.path.isabs(a) else os.path.join(workdir, a)
        break
    return interp, file, module, search, wrappers


def python_code(facts, allowed, interp_path=interpreter_path):
    entry = python_entry(facts['argv'], facts.get('workdir') or '/', facts.get('env') or {}, interp_path)
    if entry is None:
        return None
    interp, file, module, extra, wrappers = entry
    workdir = facts.get('workdir') or '/'
    pythonpath = [p for p in (facts.get('env') or {}).get('PYTHONPATH', '').split(':') if p]
    first = [os.path.dirname(os.path.realpath(file))] if file else [workdir]
    g = Graph(first + extra + pythonpath + interp_path(interp, workdir), allowed + ([os.path.dirname(os.path.realpath(file))] if file else []))
    for w in wrappers:
        g.files.add(os.path.realpath(w))
    if file:
        g.visit(file)
    elif module:
        found = g.resolve(module)
        for f in found:
            g.visit(f, g._package_of(module, f))
        main = [d for d in (g._pkg.get(module) or []) if os.path.isfile(os.path.join(d, '__main__.py'))]
        for d in main:
            g.visit(os.path.join(d, '__main__.py'), module)
    return {'kind': 'python', 'entry': file or module, 'files': g.files}


def scan_roots(roots):
    out = set()
    for root in roots:
        root = os.path.realpath(root)
        if os.path.isfile(root):
            out.add(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith('.')]
            out.update(os.path.join(dirpath, f) for f in filenames if os.path.splitext(f)[1] in CODE_EXT)
    return out


def code_for(facts, declared=None, *, walter_root=None, interp_path=interpreter_path):
    """{'kind', 'entry', 'files'} of what the unit loads (see module doc)."""
    declared = declared or {}
    roots, extra_files = declared.get('code_roots', []), declared.get('code_files', [])
    allowed = [str(walter_root or os.environ.get('WALTER_ROOT') or '/walter')] + list(roots)
    argv = facts.get('argv') or []
    out = python_code(facts, allowed, interp_path) if argv else None
    if out is None:
        exe = os.path.realpath(argv[0]) if argv else ''
        js = next((a for a in argv[1:] if os.path.splitext(a)[1] in CODE_EXT), None) if os.path.basename(exe) == 'node' else (
            exe if os.path.splitext(exe)[1] in CODE_EXT else None)
        files = set()
        if js and any(os.path.realpath(js).startswith(a.rstrip('/') + '/') for a in allowed):
            files.add(os.path.realpath(js))
            files |= scan_roots([os.path.dirname(os.path.realpath(js))])
        out = {'kind': 'node' if (js or roots) else 'external', 'entry': js, 'files': files}
    out['files'] = set(out['files']) | scan_roots(roots) | {os.path.realpath(f) for f in extra_files if os.path.isfile(f)}
    if out['kind'] == 'external' and out['files']:
        out['kind'] = 'declared'
    return out


def newest(files):
    best = (None, 0.0)
    for f in files:
        try:
            m = os.stat(f).st_mtime
        except OSError:
            continue
        if m > best[1]:
            best = (f, m)
    return best


def assess(unit, facts, declared=None, **kw):
    row = {'unit': unit, 'active': bool(facts.get('active')), 'started_at': _iso(facts.get('started_at'))}
    if facts.get('error') or not facts.get('loaded', True):
        return {**row, 'stale': None, 'kind': 'unknown', 'note': facts.get('error') or 'unit not loaded'}
    code = code_for(facts, declared, **kw)
    path, mtime = newest(code['files'])
    row.update(kind=code['kind'], entry=code['entry'], files=len(code['files']), newest=path, newest_mtime=_iso(mtime))
    if not row['active'] or not facts.get('started_at'):
        row.update(stale=None, note='not running')
    elif code['kind'] == 'external' or not path:
        row.update(stale=None, note='no Walter code loaded')
    else:
        row['stale'] = mtime > facts['started_at'] + TOLERANCE_S
        if row['stale']:
            row['behind_s'] = int(mtime - facts['started_at'])
    return row


# ---- registry ---------------------------------------------------------------------------------------------------

def declared_services(registry):
    """(long-running units -> owning module, unit -> merged service_code declaration)."""
    units, code = {}, {}
    for m in registry['modules']:
        for s in m.get('services', []):
            if s.endswith('.timer') or s.endswith('.socket'):
                continue
            units.setdefault(_unit(s), m['id'])
        for s, d in (m.get('service_code') or {}).items():
            c = code.setdefault(_unit(s), {'code_roots': [], 'code_files': []})
            c['code_roots'] += d.get('code_roots', [])
            c['code_files'] += d.get('code_files', [])
    return units, code


def status(registry=None, facts=unit_facts, **kw):
    from . import registry as reg
    registry = registry or reg.load()
    units, code = declared_services(registry)
    rows = [{**assess(u, facts(u), code.get(u), **kw), 'module': units[u]} for u in sorted(units)]
    stale = [r['unit'] for r in rows if r.get('stale')]
    return {'ok': not stale, 'checked_at': _iso(_now()), 'stale': stale, 'services': rows,
            'scope': 'start time of each declared long-running service vs the newest code it loads (static imports + declared roots)'}


# ---- the repair: gated restart --------------------------------------------------------------------------------

def _state_file():
    from . import instance
    d = Path(instance.root()) / 'state' / 'guardians'
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d / 'deploy-restarts.json'


def turns_in_flight(runner=subprocess.run):
    """Open Walter Engine runs younger than TURN_MAX_S, from Memory's run plane (walter-memory runs list).
    None when unknown: the caller must then treat the engine as busy."""
    try:
        r = runner(['walter-memory', 'runs', 'list', '--limit', '50'], capture_output=True, text=True, timeout=60)
        rows = json.loads(r.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if r.returncode or not isinstance(rows, list):
        return None
    return sum(1 for x in rows if isinstance(x, dict) and x.get('status') == 'open' and x.get('runtime') == 'dsh'
               and (x.get('seconds') or 0) < TURN_MAX_S)


def repair_enabled():
    """config/deploy.toml [repair] enabled (instance override first); off when unreadable."""
    import tomllib
    from . import instance
    try:
        return bool(tomllib.loads(Path(instance.config('core', 'deploy.toml')).read_text())
                    .get('repair', {}).get('enabled', False))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return False


def decide(row, last_restart=None, busy=None, now=None, enabled=True):
    """What the repair would do for one service: restart | defer:<reason> | none:<reason>."""
    now = now or _now()
    if not row.get('stale'):
        return 'none:fresh'
    if not enabled:
        return 'defer:repair_disabled'
    if last_restart and now - last_restart < RESTART_EVERY_S:
        return 'defer:rate_limited'
    if row['unit'] in ENGINE_UNITS and busy != 0:
        return 'defer:turn_in_flight' if busy else 'defer:engine_state_unknown'
    return 'restart'


def plan(report, *, history=None, busy=None, now=None, enabled=None):
    history = history if history is not None else _history()
    enabled = repair_enabled() if enabled is None else enabled
    need_busy = any(r.get('stale') and r['unit'] in ENGINE_UNITS for r in report['services'])
    if need_busy and busy is None:
        busy = turns_in_flight()
    return {r['unit']: decide(r, history.get(r['unit']), busy, now, enabled) for r in report['services'] if r.get('stale')}


def _history():
    try:
        return json.loads(_state_file().read_text())
    except (OSError, ValueError):
        return {}


def restart(unit, *, dry_run=False, settle=10.0, facts=unit_facts, runner=subprocess.run, registry=None, enabled=None,
            require_stale=False):
    """The guardian's allowed repair. rc 0 = restarted and fresh, nothing to do, or deferred (checked again on a later
    pass); rc 1 = restarted but still stale or not active; rc 2 = refused (not a declared service); rc 3 (only with
    require_stale: a repair whose cause must be staleness, e.g. the context guardian's degraded preflight) = the unit
    is fresh or the repair is switched off, so a restart cannot help: the guardian escalates."""
    unit = _unit(unit)
    report = status(registry, facts)
    row = next((r for r in report['services'] if r['unit'] == unit), None)
    if row is None:
        return {'ok': False, 'rc': 2, 'unit': unit, 'action': 'refused', 'reason': 'not a declared long-running service'}
    history = _history()
    enabled = repair_enabled() if enabled is None else enabled
    action = decide(row, history.get(unit), turns_in_flight(runner) if row.get('stale') and unit in ENGINE_UNITS else 0,
                    enabled=enabled)
    out = {'unit': unit, 'stale': row.get('stale'), 'newest': row.get('newest'), 'started_at': row.get('started_at'),
           'action': action, 'dry_run': dry_run, 'repair_enabled': enabled}
    if require_stale and action in ('none:fresh', 'defer:repair_disabled'):
        return {**out, 'ok': False, 'rc': 3}
    if action != 'restart' or dry_run:
        return {**out, 'ok': True, 'rc': 0}
    history[unit] = _now()
    path = _state_file()
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(history))
    tmp.replace(path)
    r = runner(['systemctl', 'restart', unit + '.service'], capture_output=True, text=True, timeout=120)
    time.sleep(settle)
    after = next((x for x in status(registry, facts)['services'] if x['unit'] == unit), {})
    ok = r.returncode == 0 and after.get('active') and not after.get('stale')
    return {**out, 'ok': bool(ok), 'rc': 0 if ok else 1, 'restart_rc': r.returncode,
            'after': {'active': after.get('active'), 'stale': after.get('stale'), 'started_at': after.get('started_at')}}


def table(report, actions=None):
    lines = [f"{'service':28} {'module':8} {'started (UTC)':20} {'newest code (UTC)':20} stale  newest file"]
    for r in report['services']:
        st = {True: 'YES', False: 'no', None: '-'}[r.get('stale')]
        lines.append(f"{r['unit'][:28]:28} {r['module'][:8]:8} {(r.get('started_at') or '-')[:19]:20} "
                     f"{(r.get('newest_mtime') or '-')[:19]:20} {st:6} {r.get('newest') or r.get('note') or ''}")
    for u, a in (actions or {}).items():
        lines.append(f'repair {u}: {a}')
    return '\n'.join(lines)
