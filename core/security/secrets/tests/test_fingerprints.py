"""Value-free vault fingerprints: masking without the values, no Bitwarden, no instance."""
import json

import pytest

from walter_secrets import fingerprints as fp

KEY = "af0d" * 8          # a bare 32-hex API key: no shape a pattern could catch


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "KEY_FILE", tmp_path / "fingerprint.key")
    monkeypatch.setattr(fp, "INDEX_FILE", tmp_path / "fingerprints.json")
    monkeypatch.setattr(fp, "_RELOAD_S", 0)
    items = [{"login": {"username": "owner@example.com", "password": "Tr0ub4dor&3x", "totp": None},
              "fields": [{"name": "api_key", "type": 1, "value": KEY}, {"name": "flag", "type": 2, "value": "true"},
                         {"name": "site", "type": 0, "value": "https://example.com/login"}],
              "card": {"number": "4970100000000063", "code": "123"}},
             {"login": {"password": "short"}, "notes": "free text with " + "n0t3-indexed-value"}]
    calls = []

    def bw(*args):
        calls.append(args)
        return json.dumps(items) if args[:2] == ("list", "items") else ""
    monkeypatch.setattr("walter_secrets.secrets_sync.bw", bw)
    fp._matcher.reset()
    out = fp.build()
    yield out, tmp_path
    fp._matcher.reset()


def test_index_holds_no_value_and_is_private(index):
    out, tmp = index
    assert out["ok"] and out["items"] == 2 and out["values"] == 3      # password, api key, card number
    raw = (tmp / "fingerprints.json").read_text()
    for secret in (KEY, "Tr0ub4dor&3x", "4970100000000063"):
        assert secret not in raw
    assert oct((tmp / "fingerprints.json").stat().st_mode)[-3:] == "600"
    assert oct((tmp / "fingerprint.key").stat().st_mode)[-3:] == "600"


@pytest.mark.parametrize("text,expected", [
    (f"voila la nouvelle clef : {KEY}", "voila la nouvelle clef : «secret:vault»"),
    (f"printf '%s' '{KEY}' | bw", "printf '%s' '«secret:vault»' | bw"),
    (f"KIE_API_KEY={KEY}", "KIE_API_KEY=«secret:vault»"),
    (f"https://api/x?key={KEY}&a=1", "https://api/x?key=«secret:vault»&a=1"),
    ("login owner:Tr0ub4dor&3x ok", "login owner:«secret:vault» ok"),
    ("carte 4970100000000063", "carte «secret:vault»"),
])
def test_known_values_are_masked_whatever_their_shape(index, text, expected):
    assert fp.scrub(text) == expected


def test_ordinary_text_and_non_secret_fields_stay(index):
    text = "owner@example.com https://example.com/login true short n0t3-indexed-value " + "0123456789abcdef" * 2
    assert fp.scrub(text) == text


def test_without_index_text_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "INDEX_FILE", tmp_path / "absent.json")
    monkeypatch.setattr(fp, "_RELOAD_S", 0)
    fp._matcher.reset()
    assert fp.scrub(f"clé {KEY}") == f"clé {KEY}"
    assert fp.status()["ok"] is False
