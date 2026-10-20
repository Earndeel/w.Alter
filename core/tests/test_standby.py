import json
import tempfile
import unittest
from pathlib import Path

from walter_platform import standby

CONFIG = '''
[groups.app]
title = "App"
units = ["db.service", "app.service"]
containers = ["side"]
ports = [3000]
idle_minutes = 30
'''


class FakeHost:
    def __init__(self):
        self.active, self.conns, self.enabled, self.calls = set(), 0, set(), []

    def unit_active(self, u): return u in self.active
    def unit_enabled(self, u): return u in self.enabled
    def container_running(self, c): return c in self.active
    def container_autostarts(self, c): return False
    def connections(self, ports): return self.conns

    def start(self, g):
        self.calls.append(('start', g['units'] + g['containers']))
        self.active |= set(g['units'] + g['containers'])
        return []

    def stop(self, g):
        self.calls.append(('stop', list(reversed(g['containers'])) + list(reversed(g['units']))))
        self.active -= set(g['units'] + g['containers'])
        return []


class StandbyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / 'standby.toml'
        self.config.write_text(CONFIG)
        self.state = Path(self.tmp.name) / 'state.json'
        self.host = FakeHost()
        self.kw = {'host': self.host, 'config': self.config, 'state': self.state}

    def tearDown(self):
        self.tmp.cleanup()

    def test_groups_are_validated(self):
        self.config.write_text('[groups.Bad]\nunits = ["x"]\n')
        with self.assertRaises(ValueError):
            standby.groups(self.config)
        self.config.write_text('[groups.x]\nports = [1]\n')
        with self.assertRaises(ValueError):
            standby.groups(self.config)
        self.config.write_text('[groups.x]\nunits = ["x"]\nports = [70000]\n')
        with self.assertRaises(ValueError):
            standby.groups(self.config)
        self.assertEqual(standby.groups(Path(self.tmp.name) / 'absent.toml'), {})

    def test_start_in_order_stop_in_reverse(self):
        standby.start('app', by='monsieur', now=100, **self.kw)
        standby.stop('app', now=200, **self.kw)
        self.assertEqual(self.host.calls, [('start', ['db.service', 'app.service', 'side']),
                                           ('stop', ['side', 'app.service', 'db.service'])])
        self.assertEqual(json.loads(self.state.read_text())['app']['stop_reason'], 'asked')
        with self.assertRaises(ValueError):
            standby.start('nope', **self.kw)

    def test_sweep_keeps_used_groups_and_stops_idle_ones(self):
        standby.start('app', now=0, **self.kw)
        self.host.conns = 1
        self.assertEqual(standby.sweep(now=40 * 60, **self.kw)['stopped'], [])     # in use: activity recorded
        self.host.conns = 0
        self.assertEqual(standby.sweep(now=60 * 60, **self.kw)['stopped'], [])     # 20 min idle < 30
        out = standby.sweep(now=71 * 60, **self.kw)
        self.assertEqual(out['stopped'], [{'group': 'app', 'stopped': True, 'failed': []}])
        self.assertFalse(standby.status(now=72 * 60, **self.kw)['groups'][0]['running'])

    def test_a_group_found_running_starts_its_idle_clock(self):
        self.host.active = {'app.service'}
        self.assertEqual(standby.sweep(now=10_000, **self.kw)['stopped'], [])
        self.assertEqual(standby.sweep(now=10_000 + 29 * 60, **self.kw)['stopped'], [])
        self.assertEqual(len(standby.sweep(now=10_000 + 31 * 60, **self.kw)['stopped']), 1)

    def test_ensure_starts_when_asleep_and_counts_as_use(self):
        self.assertTrue(standby.ensure('app', by='router', now=0, **self.kw)['started'])
        self.assertFalse(standby.ensure('app', now=25 * 60, **self.kw)['started'])
        self.assertEqual(standby.sweep(now=50 * 60, **self.kw)['stopped'], [])     # 25 min since the last use
        self.assertEqual(json.loads(self.state.read_text())['app']['started_by'], 'router')

    def test_status_flags_units_that_start_at_boot(self):
        self.host.enabled = {'app.service'}
        out = standby.status(now=0, **self.kw)
        self.assertFalse(out['ok'])
        self.assertEqual(out['groups'][0]['starts_at_boot'], ['app.service'])


if __name__ == '__main__':
    unittest.main()
