import copy
import json
import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.migrate import migrate

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://cdl:cdl@localhost:5433/postgres")
TEST_DB = "cdl_test"
TEST_API_KEY = "test-shared-secret"
TEST_SESSION_SECRET = "test-session-secret-not-for-production"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB
FIXTURE = (Path(__file__).resolve().parents[2]
           / "docs/learning/existing/samples/u3-john-real-shape.json")


@pytest.fixture(scope="session")
def test_database():
    with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=5) as admin:
        # Fresh database every session so leftover rows can never block a migration.
        admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{TEST_DB}"')
    os.environ["DATABASE_URL"] = TEST_URL
    os.environ["API_SHARED_SECRET"] = TEST_API_KEY
    os.environ["SESSION_SECRET"] = TEST_SESSION_SECRET
    migrate(TEST_URL)


@pytest.fixture
def clean_tables(test_database):
    with psycopg.connect(TEST_URL) as conn:
        conn.execute("TRUNCATE audit_log, outbox, calls, applicants, users RESTART IDENTITY CASCADE")
    os.environ["SESSION_SECRET"] = TEST_SESSION_SECRET  # a test may monkeypatch it away
    os.environ["SESSION_COOKIE_SECURE"] = "0"  # the test client speaks plain http


@pytest.fixture
def client(clean_tables):
    from app.main import app
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


@pytest.fixture
def db(clean_tables):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture
def payload():
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
