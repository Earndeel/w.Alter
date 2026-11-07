"""Offline tests; integration evidence is generated separately against real Colab."""
import importlib.util
from pathlib import Path
import unittest
import hashlib
import tempfile

class ChunkTests(unittest.TestCase):
    def test_binary_chunks_roundtrip_with_small_bounded_chunks(self):
        path = Path(__file__).with_name('transfer.py')
        spec = importlib.util.spec_from_file_location('transfer', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, 'iter_chunks'), 'Bounded transfer not implemented')
        with tempfile.TemporaryDirectory() as root:
            data = bytes(range(256)) * 19
            p = Path(root) / 'test.bin'
            p.write_bytes(data)
            chunks = list(mod.iter_chunks(p, 1024))
            self.assertEqual(b''.join(chunks), data)
            self.assertTrue(all(len(c) <= 1024 for c in chunks))
            self.assertEqual(mod.sha256_file(p), hashlib.sha256(data).hexdigest())
            with self.assertRaises(ValueError):
                list(mod.iter_chunks(p, 0))

class TargetTests(unittest.TestCase):
    def test_rejects_wrong_notebook_before_transfer(self):
        spec=importlib.util.spec_from_file_location('transfer',Path(__file__).with_name('transfer.py'))
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod,'check_target'), 'Target binding is missing')
        mod.check_target({'origin':'https://colab.research.google.com','path':'/drive/expected'},'expected')
        for info in ({'origin':'https://other.invalid','path':'/drive/expected'}, {'origin':'https://colab.research.google.com','path':'/drive/other'}):
            with self.subTest(info=info), self.assertRaises(ValueError):
                mod.check_target(info,'expected')

class NameTests(unittest.TestCase):
    def test_credential_like_names_are_rejected_case_insensitively(self):
        spec=importlib.util.spec_from_file_location('transfer',Path(__file__).with_name('transfer.py'))
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for name in ['google_client_secret.json','oauth-refresh-token.json','CREDENTIALS.json','user-api-key.json']:
            with self.subTest(name=name),self.assertRaises(ValueError):m.safe_filename(name)

    def test_transport_exists_and_accepts_only_simple_leaf_names(self):
        path = Path(__file__).with_name('transfer.py')
        self.assertTrue(path.exists(), 'Mount-free transport not implemented')
        spec = importlib.util.spec_from_file_location('transfer', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.safe_filename('walter-comfy-dependencies-v1.tar.gz'), 'walter-comfy-dependencies-v1.tar.gz')
        for invalid in ('../secret', '/etc/passwd', '.env', 'google_token.json', 'a/b', 'a\\b', '', 'x\x00y'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mod.safe_filename(invalid)

if __name__ == '__main__':
    unittest.main()
