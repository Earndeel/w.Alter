"""Offline regression: unprepared GPU production must never reach Colab.

This suite deliberately tests a fail-closed interlock, not model readiness or
inference. All runtime objects are test doubles; there is no live allocation.
"""
from dataclasses import replace
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_on_demand import FakeBridge, SCRATCH, load_cli


class PreparationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_included_units_opt_in_cannot_bypass_preparation(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            script = root / 'job.py'
            script.write_text('pass\n')
            for device in ('T4', 'L4', 'A100'):
                with self.subTest(device=device):
                    destination = root / ('results-' + device)
                    args = cli.parse_args(['job', str(script), '--device', device,
                        '--allow-included-units', '--result-dir', str(destination)])
                    with self.assertRaisesRegex(ValueError, 'preparation'):
                        cli.prepare_job(args)
                    self.assertFalse(destination.exists())

    async def test_invalid_or_missing_sources_do_not_override_preparation_refusal(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            args = cli.parse_args(['job', str(root / 'missing.py'), '--device', 'A100',
                '--allow-included-units', '--result-dir', str(root / 'results')])
            with self.assertRaisesRegex(ValueError, 'preparation'):
                cli.prepare_job(args)
            self.assertFalse((root / 'results').exists())

    async def test_execute_refuses_before_config_or_browser_or_bridge(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            script = root / 'job.py'
            script.write_text('pass\n')
            args = cli.parse_args(['job', str(script), '--device', 'L4',
                '--allow-included-units', '--result-dir', str(root / 'results')])
            def forbidden(*args):
                self.fail('Unprepared GPU job must not construct a browser or bridge')
            with self.assertRaisesRegex(ValueError, 'preparation'):
                await cli.execute(args, config={}, browser_factory=forbidden, bridge_factory=forbidden)
            self.assertFalse((root / 'results').exists())

    async def test_direct_run_prepared_entry_cannot_bypass_gate(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            script = root / 'job.py'
            script.write_text('pass\n')
            cpu = cli.prepare_job(cli.parse_args(['job', str(script), '--result-dir', str(root / 'results')]))
            for device in ('T4', 'L4', 'A100'):
                with self.subTest(device=device):
                    gpu = replace(cpu, device=device, allow_included_units=True)
                    bridge = FakeBridge()
                    with self.assertRaises(cli.OnDemandError) as caught:
                        await cli.run_prepared(gpu, bridge)
                    self.assertEqual(bridge.events, [])
                    self.assertFalse(caught.exception.report['cleanup']['attempted'])
                    self.assertEqual(caught.exception.report['status'], 'error')

    def test_cli_reports_authored_block_reason_and_no_allocation(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as temporary:
            root = Path(temporary)
            script = root / 'job.py'
            script.write_text('pass\n')
            stdout, stderr = io.StringIO(), io.StringIO()
            # Isolate config and prohibit Browser even on the pre-fix RED path.
            with patch.object(cli, 'ROOT', root), \
                 patch.object(cli.transfer, 'Browser', side_effect=AssertionError('Live browser forbidden')), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(['job', str(script), '--device', 'A100', '--allow-included-units',
                    '--result-dir', str(root / 'results')])
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), '')
            report = json.loads(stderr.getvalue())
            self.assertEqual(report['status'], 'blocked')
            self.assertEqual(report['reason'], 'gpu_preparation_incomplete')
            self.assertFalse(report['allocation_requested'])
            self.assertFalse(report['cleanup']['attempted'])
            self.assertIsNone(report['compute_units_consumed'])
            self.assertFalse((root / 'results').exists())


if __name__ == '__main__':
    unittest.main()
