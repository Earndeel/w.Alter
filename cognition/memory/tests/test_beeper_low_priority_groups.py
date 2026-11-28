"""27/11/2026 (Monsieur, amends D4): a group moved to Low priority in Beeper is not ingested; nothing else changes."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("beeper_conn_lp", Path(__file__).resolve().parent.parent / "connectors/beeper.py")
beeper = importlib.util.module_from_spec(spec); spec.loader.exec_module(beeper)


class Boom:
    """Any read of the source or the database fails the test: an excluded chat must not even be fetched."""
    checkpoint_scope = "test"

    def __getattr__(self, name):
        raise AssertionError(f"excluded chat touched the source: {name}")


def test_low_priority_group_is_excluded_and_never_read():
    chat = {"id": "!g:test", "type": "group", "isLowPriority": True, "isMuted": True}
    assert beeper.excluded(chat) == "low_priority_group"
    assert beeper.store_messages(chat, [{"id": "1", "timestamp": "2026-11-27T12:00:00Z"}], conn=Boom()) == (0, 0)
    assert beeper.sync_chat(Boom(), chat, backfill_pages=5) == (0, 0)
    assert beeper.reconcile_chat(Boom(), chat, since=None) == (0, 0)


def test_other_chats_are_still_ingested():
    assert beeper.excluded({"type": "group", "isMuted": True}) is None              # muted alone: he may still write there
    assert beeper.excluded({"type": "group", "isArchived": True}) is None
    assert beeper.excluded({"type": "single", "isLowPriority": True}) is None       # one-to-one chats never excluded here
    assert beeper.excluded({"type": "group"}) is None
