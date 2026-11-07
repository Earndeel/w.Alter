"""Standby: services that sleep until needed, start on demand, and stop after a period without use.

A group (one project or one capability) lists its systemd units and/or Docker containers, the local TCP ports whose
established connections mean "in use", and how long it may stay idle. Groups are instance settings
(`config/core/standby.toml`, `walter instance config core standby.toml`); the shipped default has none.

    [groups.<name>]
    title = "..."
    units = ["a.service", "b.service"]      # started in this order, stopped in reverse
    containers = ["c"]                       # docker start / stop
    ports = [3000]                           # established connections on these local ports = activity
    idle_minutes = 120                       # stop after this long without activity (default 60)

`start` / `stop` act at once; `ensure` (for a module that needs the service) starts it if asleep and counts as use;
`sweep` (timer, every few minutes) records activity and stops idle groups. State (last activity, who started it) is
kept in the instance (`state/core/standby.json`). Units in standby must not start at boot: `status` flags them.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import tomllib
from pathlib import Path

from . import instance

DEFAULT_IDLE = 60
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,40}\Z")


def _run(argv, timeout=120):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


# ── settings and state ─────────────────────────────────────────────────────────────────────────────────────
def groups(config=None) -> dict:
    path = Path(config) if config else instance.config('core', 'standby.toml')
    doc = tomllib.loads(path.read_text()) if path.is_file() else {}
    out = {}
    for name, g in (doc.get('groups') or {}).items():
        if not NAME.match(name) or not isinstance(g, dict):
            raise ValueError('invalid standby group name: ' + str(name))
        units, containers = g.get('units', []), g.get('containers', [])
        if not units and not containers:
            raise ValueError(f'standby group {name}: units or containers required')
        ports = g.get('ports', [])
        if not all(isinstance(p, int) and 0 < p < 65536 for p in ports):
            raise ValueError(f'standby group {name}: ports must be TCP port numbers')
        out[name] = {'title': g.get('title', name), 'units': list(units), 'containers': list(containers),
                     'ports': list(ports), 'idle_minutes': int(g.get('idle_minutes', DEFAULT_IDLE))}
    return out


def _state_path(state=None) -> Path:
    return Path(state) if state else instance.state('core', 'standby.json')


def _load(state=None) -> dict:
    p = _state_path(state)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _save(data, state=None) -> None:
    p = _state_path(state)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    tmp.replace(p)


# ── observation ────────────────────────────────────────────────────────────────────────────────────────────
class Host:
    """systemd, Docker and socket observation; replaced in tests."""

    def unit_active(self, unit) -> bool:
        return _run(['systemctl', 'is-active', '--quiet', unit], 30).returncode == 0

    def unit_enabled(self, unit) -> bool:
        """Started at boot: 'enabled' only ('static' units have no install section and do not start by themselves)."""
        return _run(['systemctl', 'is-enabled', unit], 30).stdout.strip() in ('enabled', 'enabled-runtime')

    def container_running(self, name) -> bool:
        r = _run(['docker', 'inspect', '-f', '{{.State.Running}}', name], 30)
        return r.returncode == 0 and r.stdout.strip() == 'true'

    def container_autostarts(self, name) -> bool:
        r = _run(['docker', 'inspect', '-f', '{{.HostConfig.RestartPolicy.Name}}', name], 30)
        return r.returncode == 0 and r.stdout.strip() in ('always', 'unless-stopped')

    def connections(self, ports) -> int:
        if not ports:
            return 0
        flt = ' or '.join(f'sport = :{p}' for p in ports)
        r = _run(['ss', '-Htn', 'state', 'established', f'( {flt} )'], 30)
        return len([line for line in r.stdout.splitlines() if line.strip()]) if r.returncode == 0 else 0

    def start(self, g) -> list[str]:
        errors = []
        for u in g['units']:
            if _run(['systemctl', 'start', u], 300).returncode:
                errors.append(u)
        for c in g['containers']:
            if _run(['docker', 'start', c], 300).returncode:
                errors.append(c)
        return errors

    def stop(self, g) -> list[str]:
        errors = []
        for c in reversed(g['containers']):
            if _run(['docker', 'stop', c], 300).returncode:
                errors.append(c)
        for u in reversed(g['units']):
            if _run(['systemctl', 'stop', u], 300).returncode:
                errors.append(u)
        return errors


def _last(s):
    """Latest of the last use and the last start, or None when the group was never seen."""
    seen = [s[k] for k in ('last_activity', 'started_at') if isinstance(s.get(k), (int, float))]
    return max(seen) if seen else None


def _running(host, g) -> bool:
    return any(host.unit_active(u) for u in g['units']) or any(host.container_running(c) for c in g['containers'])


def _row(name, g, host, st, now):
    running = _running(host, g)
    conns = host.connections(g['ports']) if running else 0
    s = st.get(name, {})
    last = _last(s)
    idle = int(now - last) if last is not None else None
    boot = [u for u in g['units'] if host.unit_enabled(u)] + [c for c in g['containers'] if host.container_autostarts(c)]
    row = {'group': name, 'title': g['title'], 'running': running, 'connections': conns,
           'idle_minutes_allowed': g['idle_minutes'], 'idle_seconds': idle, 'started_by': s.get('started_by'),
           'starts_at_boot': boot}
    if running and conns == 0 and idle is not None:
        row['stops_in_seconds'] = max(0, g['idle_minutes'] * 60 - idle)
    return row


# ── actions ────────────────────────────────────────────────────────────────────────────────────────────────
def status(*, host=None, config=None, state=None, now=None) -> dict:
    host, now = host or Host(), time.time() if now is None else now
    st = _load(state)
    rows = [_row(n, g, host, st, now) for n, g in groups(config).items()]
    return {'ok': not any(r['starts_at_boot'] for r in rows), 'groups': rows}


def _group(name, config):
    found = groups(config).get(name)
    if found is None:
        raise ValueError('unknown standby group: ' + str(name))
    return found


def start(name, *, by='agent', host=None, config=None, state=None, now=None) -> dict:
    host, now, g = host or Host(), time.time() if now is None else now, _group(name, config)
    errors = host.start(g)
    st = _load(state)
    st[name] = {**st.get(name, {}), 'started_at': now, 'last_activity': now, 'started_by': by}
    _save(st, state)
    return {'ok': not errors, 'group': name, 'started': not errors, 'failed': errors}


def stop(name, *, reason='asked', host=None, config=None, state=None, now=None) -> dict:
    host, now, g = host or Host(), time.time() if now is None else now, _group(name, config)
    errors = host.stop(g)
    st = _load(state)
    st[name] = {**st.get(name, {}), 'stopped_at': now, 'stop_reason': reason}
    _save(st, state)
    return {'ok': not errors, 'group': name, 'stopped': not errors, 'failed': errors}


def ensure(name, *, by='module', host=None, config=None, state=None, now=None) -> dict:
    """For a caller that needs the service: start it if asleep; either way, this counts as use."""
    host, now, g = host or Host(), time.time() if now is None else now, _group(name, config)
    if not _running(host, g):
        return start(name, by=by, host=host, config=config, state=state, now=now)
    st = _load(state)
    st[name] = {**st.get(name, {}), 'last_activity': now}
    _save(st, state)
    return {'ok': True, 'group': name, 'started': False}


def sweep(*, host=None, config=None, state=None, now=None) -> dict:
    """Record activity of running groups and stop those idle longer than allowed."""
    host, now = host or Host(), time.time() if now is None else now
    st, done = _load(state), []
    for name, g in groups(config).items():
        if not _running(host, g):
            continue
        s = st.setdefault(name, {})
        if host.connections(g['ports']) > 0:
            s['last_activity'] = now
            continue
        last = _last(s)
        if last is None:                   # running before standby knew it: start counting now
            s['last_activity'] = now
            continue
        if now - last >= g['idle_minutes'] * 60:
            errors = host.stop(g)
            s.update(stopped_at=now, stop_reason='idle')
            done.append({'group': name, 'stopped': not errors, 'failed': errors})
    _save(st, state)
    return {'ok': all(d['stopped'] for d in done), 'stopped': done}
