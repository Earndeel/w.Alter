"""Memory V1 end to end (test database): a decision taken in one runtime is extracted, indexed and served by the
memory context in a new session of another runtime; a correction replaces it; a local_only decision never comes out
of the cloud-safe context. Real local embeddings (no network), scripted extraction model, rerank off."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import context, events, extract2, search

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(search, "_rerank", lambda q, results, limit, timeout=8: results[:limit])
    extract2.set_v1_start(NOW - timedelta(days=1))
    from walter_memory import ingestion
    ingestion.register_connector("search_indexer", "walter", "agent", "pytest", timedelta(minutes=10))


RUN = uuid.uuid4().hex[:6]     # this run's own project: earlier runs on the same test database are other projects


def model(messages, **kw):
    prompt = messages[0]["content"]
    part = prompt.split("seuls citables) :", 1)[1].split("\n\nRends un JSON", 1)[0]
    known = dict(re.findall(r"^(K\d+)\. \[[^\]]+\] (.*)$", prompt, re.M))
    items = []
    for i, line in enumerate([l for l in part.strip().splitlines() if re.match(r"^\d+\. \[", l)], 1):
        m = "[Monsieur" in line and re.search(r"(le serveur de démo (?:tournera|tourne finalement) sur (\w+))", line)
        if m:
            sup = [k for k, v in known.items() if "serveur de démo" in v and "Zéphyr" in v and RUN in v]
            items.append({"kind": "decision", "text": f"Le serveur de démo du projet Zéphyr {RUN} tourne sur {m.group(2)}",
                          "state": "decided", "msgs": [i], "quote": m.group(1), "supersedes": sup})
    return {"content": json.dumps({"summary": "", "items": items}), "cost_usd": 0, "model": "scripted"}


def say(source, thread, text, at, privacy="cloud_allowed"):
    events.record_events([{"event_type": "message.sent", "source": source, "source_account": "pytest",
                           "source_id": uuid.uuid4().hex, "thread_id": thread, "occurred_at": at, "content": text,
                           "privacy_class": privacy}])


def knowledge(query):
    return context.get_context(query, include_profile=False)["text"]


def _decide(state, questions, **kw):
    """Scripted Walter Decision (memory.reconcile): a statement about this run's demo server replaces the earlier one."""
    ans = {}
    for sid, st in state["statements"].items():
        crit = {k: v for k, v in questions[f"{sid}_target"]["criteria"].items() if k != "none"}
        k = next((k for k, v in crit.items() if RUN in v and "serveur de démo" in v and v != st["text"]), None)
        ans[f"{sid}_target"] = {"choice": k or "none", "confidence": 0.9}
        ans[f"{sid}_verdict"] = {"choice": "replaces" if k else "new", "confidence": 0.9}
    return {"answers": ans, "model": "scripted-decision"}


@pytest.mark.real_reconcile
def test_decision_under_hermes_is_found_by_codex_after_a_new_session_and_corrections_win(monkeypatch):
    from walter_memory import llm
    from walter_memory.db import connection
    monkeypatch.setattr(llm, "decide", _decide)
    with connection() as conn:      # earlier runs' demo servers (test database only) are not this run's knowledge
        conn.execute("""update core.derived_items set status = 'retracted' where derived_by = 'l3.extract'
                        and content like 'Le serveur de démo du projet Zéphyr %%' and content not like %s
                        and status in ('derived', 'verified')""", (f"%{RUN}%",))
    t1, t2 = f"h-{uuid.uuid4().hex[:8]}", f"c-{uuid.uuid4().hex[:8]}"
    say("hermes", t1, "Pour le projet Zéphyr, le serveur de démo tournera sur Hetzner, c'est décidé.", NOW - timedelta(hours=5))
    extract2.process_thread("hermes", t1, chat=model)
    search.index_pending()
    # a new Codex session (new thread, other runtime) asks about it
    assert "Hetzner" in knowledge("Sur quel serveur tourne la démo du projet Zéphyr ?")
    # later, in Claude Code, the owner changes his mind
    say("claude_code", t2, "Changement : le serveur de démo tourne finalement sur Scaleway pour Zéphyr.", NOW - timedelta(hours=2))
    extract2.process_thread("claude_code", t2, chat=model)
    search.index_pending()
    text = knowledge("Sur quel serveur tourne la démo du projet Zéphyr ?")
    assert "Scaleway" in text and "Hetzner" not in text


def test_local_only_never_comes_out_of_the_cloud_safe_context():
    t = f"w-{uuid.uuid4().hex[:8]}"
    say("hermes", t, "le serveur de démo tournera sur Ovhprivé pour le projet Orion", NOW - timedelta(hours=3), "local_only")
    extract2.process_thread("hermes", t, chat=model)
    search.index_pending()
    assert "Ovhprivé" not in knowledge("serveur de démo du projet Orion")
