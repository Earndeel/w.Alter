"""walter-secret store (owner, 2026-10-28): Walter writes the logins / API keys it creates into the vault.
A fake `bw` stands in for Bitwarden: nothing reaches the real vault. The value must never be on a command line
and never in the output."""
import base64
import io
import json
import subprocess

import pytest

from walter_secrets import cli, vault
from walter_secrets.vault import Vault, SecretError

SECRET = "s3cr3t-VALUE-never-printed-123"


class FakeBw:
    def __init__(self):
        self.items, self.argvs = [{"id": "i0", "name": "existing", "type": 1, "login": {"password": "old"}}], []

    def __call__(self, argv, input=None, **kw):
        self.argvs.append(argv)
        a = argv[1:-1]                                 # drop "bw" and "--nointeraction"
        out = ""
        if a[:2] == ["list", "items"]:
            out = json.dumps(self.items)
        elif a == ["sync"]:
            out = ""
        elif a[:2] == ["create", "item"]:
            item = json.loads(base64.b64decode(input)); item["id"] = f"i{len(self.items)}"; self.items.append(item)
            out = json.dumps(item)
        elif a[:2] == ["get", "item"]:
            out = json.dumps(next(i for i in self.items if i["id"] == a[2]))
        elif a[:2] == ["edit", "item"]:
            item = json.loads(base64.b64decode(input))
            self.items = [item if i["id"] == item["id"] else i for i in self.items]; out = json.dumps(item)
        return subprocess.CompletedProcess(argv, 0, out, "")


@pytest.fixture
def bw(monkeypatch):
    fake = FakeBw()
    v = Vault()
    monkeypatch.setattr(v, "_session", lambda stale=None: "session")
    monkeypatch.setattr(vault.subprocess, "run", fake)
    monkeypatch.setattr(cli, "VAULT", v)
    monkeypatch.setattr(cli, "audit", lambda *a, **k: None)
    return fake, v


def test_create_api_key_value_only_on_stdin(bw):
    fake, v = bw
    out = v.store("svc API", "api_key", SECRET, uris=["https://svc.example"], fields={"created_by": "walter"})
    assert out["created"] and out["field"] == "password" and out["reference"] == "{{bw:i1:password}}"
    assert all(SECRET not in " ".join(a) for a in fake.argvs)                       # never on a command line
    item = fake.items[-1]
    assert item["login"]["password"] == SECRET and {"name": "kind", "value": "api_key", "type": 0} in item["fields"]
    assert SECRET not in json.dumps(out)


def test_duplicate_needs_update_and_update_replaces_value(bw):
    fake, v = bw
    with pytest.raises(SecretError, match="--update"):
        v.store("existing", "login", "x")
    out = v.store("existing", "login", "new-value", update=True)
    assert out["updated"] and fake.items[0]["login"]["password"] == "new-value"


def test_note_and_bad_kind(bw):
    fake, v = bw
    v.store("a note", "note", "line1\nline2")
    assert fake.items[-1]["type"] == 2 and fake.items[-1]["notes"] == "line1\nline2"
    with pytest.raises(SecretError):
        v.store("x", "card", "1")


def test_cli_generate_and_stdin_never_print_the_value(bw, monkeypatch, capsys):
    fake, v = bw
    assert cli.main(["store", "gen login", "--kind", "login", "--username", "walter", "--generate", "24"]) == 0
    out = json.loads(capsys.readouterr().out)
    generated = fake.items[-1]["login"]["password"]
    assert out["generated"] and len(generated) == 24 and generated not in json.dumps(out)
    monkeypatch.setattr("sys.stdin", io.StringIO(SECRET + "\n"))
    assert cli.main(["store", "piped key", "--kind", "api_key"]) == 0
    printed = capsys.readouterr().out
    assert SECRET not in printed and fake.items[-1]["login"]["password"] == SECRET
