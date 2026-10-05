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
    migrate(TEST_URL)


@pytest.fixture
def clean_tables(test_database):
    with psycopg.connect(TEST_URL) as conn:
        conn.execute("TRUNCATE calls, applicants RESTART IDENTITY CASCADE")


@pytest.fixture
def client(clean_tables):
    from app.main import app
    return TestClient(app)


@pytest.fixture
def db(clean_tables):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture
def payload():
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
