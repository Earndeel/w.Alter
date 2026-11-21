"""Importing a live proof must never allocate or contact Colab."""
import runpy
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent

class ImportSafetyTests(unittest.TestCase):
    def test_integration_proof_imports_do_not_execute_network_or_subprocesses(self):
        for name in ('test_bootstrap.py','test_runner.py','test_fresh_runtime.py'):
            with self.subTest(script=name):
                with patch('subprocess.run',side_effect=AssertionError('Live subprocess during test import')), \
                     patch('urllib.request.urlopen',side_effect=AssertionError('Live network during test import')):
                    runpy.run_path(str(ROOT/name),run_name='import_safety_probe')

if __name__=='__main__':unittest.main()
