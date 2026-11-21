"""A fresh process reads its first key without waiting for a server sync (18/11, walter-llm cold start)."""
import json
import threading

from walter_secrets import grants, vault


def test_first_read_lists_the_local_copy_and_syncs_behind(monkeypatch):
    calls, synced = [], threading.Event()
    item = {"id": "i1", "name": "k", "type": 1, "login": {"password": "x"}}

    def bw(self, *args, timeout=120):
        calls.append(args[0])
        if args[0] == "sync":
            synced.set()
            return ""
        return json.dumps([item])
    monkeypatch.setattr(vault.Vault, "_bw", bw)
    v = vault.Vault()
    assert [i["id"] for i in v.items()] == ["i1"]
    assert calls[0] == "list"                       # the local copy first, never a sync before the first answer
    assert synced.wait(2) and calls.count("list") == 2   # the server sync then a fresh list, behind it
    v.items()
    assert calls.count("sync") == 1                 # not again before SYNC_TTL


def test_the_instance_root_is_asked_once_for_many_cards(monkeypatch):
    asked = []
    monkeypatch.delenv("WALTER_GRANTS_DIR", raising=False)
    monkeypatch.setattr(grants, "_INSTANCE", {"at": 0.0, "root": None})
    monkeypatch.setattr(grants.settings, "_walter_instance", lambda *a: asked.append(a) or __import__("pathlib").Path("/x"))
    for _ in range(23):
        grants.accounts_dir()
    assert len(asked) == 1
