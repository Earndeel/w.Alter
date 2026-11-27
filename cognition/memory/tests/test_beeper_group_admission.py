"""27/11/2026 (Monsieur): a group enters memory only when it is his — pinned, small, or he writes / is mentioned there."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("beeper_conn_adm", Path(__file__).resolve().parent.parent / "connectors/beeper.py")
beeper = importlib.util.module_from_spec(spec); spec.loader.exec_module(beeper)

ME = "@me:beeper.com"


class History:
    """Stands for core.events: answers whether Monsieur wrote / was mentioned in the stored history of the chat."""

    def __init__(self, found: bool):
        self.found, self.calls = found, []

    def execute(self, sql, params):
        self.calls.append(params)
        found = self.found

        class R:
            def fetchone(self):
                return {"?column?": 1} if found else None
        return R()


class Boom:
    def __getattr__(self, name):
        raise AssertionError("the database must not be asked: the chat itself decides")


def group(total, **kw):
    return {"id": "!g:test", "type": "group", "participants": {"total": total, "items": [{"id": ME, "isSelf": True}]}, **kw}


def msg(**kw):
    return {"id": "1", "timestamp": "2026-11-27T12:00:00Z", "senderID": "@x:test", **kw}


def test_one_to_one_and_small_and_pinned_groups_are_admitted_without_a_query():
    assert beeper.group_admission({"type": "single"}, [], conn=Boom()) == "single"
    assert beeper.group_admission(group(5), [msg()], conn=Boom()) == "small_group"
    assert beeper.group_admission(group(300, isPinned=True), [msg()], conn=Boom()) == "pinned"


def test_a_large_group_he_only_reads_is_not_admitted_and_nothing_is_stored():
    chat = group(239)
    db = History(False)
    assert beeper.group_admission(chat, [msg()], conn=db) is None
    assert beeper.store_messages(chat, [msg()], conn=db) == (0, 0)


def test_his_own_message_or_a_mention_lets_the_group_in():
    assert beeper.group_admission(group(239), [msg(isSender=True, senderID=ME)], conn=Boom()) == "owner_writes"
    assert beeper.group_admission(group(239), [msg(mentions=[ME])], conn=Boom()) == "owner_mentioned"


def test_stored_history_keeps_a_group_he_takes_part_in():
    db = History(True)
    assert beeper.group_admission(group(16), [msg()], conn=db) == "owner_history"
    chat_id, days, me = db.calls[0]
    assert (chat_id, days, me) == ("!g:test", beeper.OWNER_WINDOW_DAYS, [ME])


def test_low_priority_stays_out_even_when_he_is_mentioned():
    chat = group(3, isLowPriority=True, isPinned=True)
    assert beeper.group_admission(chat, [msg(isSender=True)], conn=Boom()) is None
