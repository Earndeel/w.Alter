"""Tests never touch the production database: a throwaway database on the memory test server (127.0.0.1:5440,
tests/testdb.sh of Walter Memory), created for the run and dropped at the end."""
import os
import re
import sys
from pathlib import Path

import json

import httpx
import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADMIN = os.environ.get("WALTER_DEVBOARD_TEST_ADMIN_URL", "postgresql://hindsight:walter-test-only@127.0.0.1:5440/postgres")
if re.search(r"[:@/]5433\b", ADMIN):
    raise pytest.UsageError("devboard tests refuse the production database (port 5433)")
NAME = f"devboard_test_{os.getpid()}"
os.environ["WALTER_DEVBOARD_DATABASE_URL"] = ADMIN.rsplit("/", 1)[0] + "/" + NAME


@pytest.fixture(scope="session", autouse=True)
def database():
    try:
        admin = psycopg.connect(ADMIN, autocommit=True, connect_timeout=3)
    except Exception:
        pytest.skip("test database down: /walter/cognition/memory/tests/testdb.sh up")
    admin.execute(f'drop database if exists "{NAME}"')
    admin.execute(f'create database "{NAME}"')
    from walter_devboard import db
    db.migrate()
    yield
    db.close()
    admin.execute(f'drop database if exists "{NAME}" with (force)')
    admin.close()


@pytest.fixture
def conn(database):
    from walter_devboard import db
    with db.connection() as c:
        c.execute("""truncate devboard.cards, devboard.card_evidence, devboard.card_links, devboard.corrections,
                     devboard.documents, devboard.sections, devboard.decisions, devboard.decision_links,
                     devboard.readings, devboard.sessions, devboard.activity, devboard.live, devboard.state
                     restart identity cascade""")
    with db.connection() as c:
        yield c


def subs(*percents, age=10.0):
    return [{"id": "openai-plus", "meter": {"used_percent": 1.0, "age_s": age}}] + [
        {"id": "anthropic-pro" + ("" if i == 0 else f"-{i + 1}"), "meter": {"used_percent": p, "age_s": age}}
        for i, p in enumerate(percents)]


@pytest.fixture
def router(monkeypatch):
    from walter_devboard import llm
    state = {"pick": {"model_id": "claude-haiku-5-5", "provider": "claude-pro"}, "subs": subs(49.0), "calls": []}

    def fake(*args):
        state["calls"].append(args)
        if args[0] == "pick":
            return state["pick"]
        if args[:2] == ("subscriptions", "show"):
            return state["subs"]
        if args[:2] == ("subscriptions", "refresh"):
            return {}
        raise AssertionError(args)
    monkeypatch.setattr(llm, "_router", fake)
    monkeypatch.setenv("WALTER_LLM_TOKEN", "test-token")
    return state


@pytest.fixture
def gateway(monkeypatch):
    from walter_devboard import llm
    """Queue of (content, route header) answers; every POST body is kept."""
    state = {"answers": [], "posts": []}

    def handler(request: httpx.Request):
        state["posts"].append(json.loads(request.content))
        answer = state["answers"].pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):                       # a gateway error status
            return httpx.Response(answer, json={"detail": "every route failed"})
        content, route = answer
        return httpx.Response(200, headers={"X-Walter-Route": route},
                              json={"choices": [{"message": {"content": content}}]})
    monkeypatch.setattr(llm, "_transport", lambda: httpx.MockTransport(handler))
    return state


