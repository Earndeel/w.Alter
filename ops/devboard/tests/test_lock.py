"""Only one reading pass at a time: the timer's `due` gives way while a backfill (or another pass) holds the lock."""
import json

from walter_devboard import cli, db


def test_due_gives_way_to_a_running_pass(capsys):
    with db.autocommit() as other:
        assert db.try_lock(other)
        assert cli.main(["due"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out == {"busy": True}
    with db.autocommit() as again:
        assert db.try_lock(again)                         # released with the connection
