"""Offline concurrency guard: an overlapping CLI cannot touch the browser."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import on_demand as cli

class ControllerLockTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(cli,'notebook_lock',None)), 'Notebook serialization guard is missing')

    def test_overlapping_command_is_rejected_before_browser_construction(self):
        with tempfile.TemporaryDirectory(dir='/root/.hermes/cache/scratch') as temporary:
            root=Path(temporary)
            script=root/'job.py'
            script.write_text('pass\n')
            args=cli.parse_args(['job',str(script),'--result-dir',str(root/'results')])
            with patch.object(cli,'LOCK_DIR',root/'locks',create=True):
                with cli.notebook_lock('test-notebook'):
                    with self.assertRaisesRegex(ValueError,'already running'):
                        asyncio.run(cli.execute(args,config={'browser_session':'offline','notebook_id':'test-notebook'},browser_factory=lambda *_:self.fail('Overlapping command contacted browser')))
                with cli.notebook_lock('test-notebook'):
                    pass

    def test_lock_released_after_exception_and_symlink_refused(self):
        with tempfile.TemporaryDirectory(dir='/root/.hermes/cache/scratch') as temporary:
            root=Path(temporary)
            with patch.object(cli,'LOCK_DIR',root/'locks',create=True):
                with self.assertRaises(RuntimeError):
                    with cli.notebook_lock('test-notebook'):
                        raise RuntimeError('offline failure')
                with cli.notebook_lock('test-notebook'):
                    pass
                lock=root/'locks/test-notebook.lock'
                lock.unlink()
                lock.symlink_to(root/'outside')
                with self.assertRaises(ValueError):
                    with cli.notebook_lock('test-notebook'):
                        self.fail('Symlink lock accepted')

if __name__=='__main__':unittest.main()
