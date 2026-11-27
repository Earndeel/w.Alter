"""Secret gate shapes (2026-11-27): a private key block with key material refuses, the bare header does not.

The fixtures are built at runtime (concatenation) so this file itself never carries a credential shape: the gate
scans every published blob, tests included."""
from walter_backup import secret_gate as G

HEADER = "-----BEGIN " + "OPENSSH PRIVATE KEY" + "-----"
BODY = "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW" + "Q" * 8


def hit(text):
    return bool(G.PATTERNS.search(text))


def test_bare_header_as_in_a_detector_test_does_not_refuse():
    # the line that blocked every publication on 2026-11-27 (core/tests/test_exposure.py)
    assert not hit('self.assertEqual(E.secrets_in("' + HEADER + '"), 1)')
    assert not hit("A key file starts with " + HEADER + " then base64 lines.")


def test_key_material_refuses_with_real_or_escaped_line_breaks():
    assert hit(HEADER + "\n" + BODY + "\n")
    assert hit(HEADER + "\r\n" + BODY)
    assert hit('{"key": "' + HEADER + "\\n" + BODY + '\\n"}')        # pasted into JSON / a .env
    pem = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
    assert hit(pem + "\nProc-Type: 4,ENCRYPTED\nDEK-Info: AES-128-CBC,0011\n\n" + BODY)


def test_token_shapes_still_refuse():
    assert hit("x = 'ghp_" + "a" * 36 + "'")
    assert hit("AKIA" + "A" * 16)
    assert not hit("NAME=walter # just a comment")
