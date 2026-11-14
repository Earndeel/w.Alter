"""Tests never touch the production database: a throwaway database on the memory test server (127.0.0.1:5440,
tests/testdb.sh of Walter Memory), created for the run and dropped at the end."""
import os
import re
import sys
from pathlib import Path

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
