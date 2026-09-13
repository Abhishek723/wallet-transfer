import os
import secrets
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from wallet_service.app import create_app
from wallet_service.config import Settings
from wallet_service.db import migrate, token_hash


@pytest.fixture
def settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated = make_conninfo(url, options=f"-csearch_path={schema}")
    migrate(isolated)
    yield Settings(isolated, pool_size=12, lock_timeout_ms=2000)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def user_factory(settings):
    def create(balance=None):
        user = {"id": uuid4(), "token": secrets.token_urlsafe(32), "wallet_id": uuid4()}
        user["headers"] = {"Authorization": f"Bearer {user['token']}"}
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(
                "INSERT INTO users (id, name, token_hash) VALUES (%s, %s, %s)",
                (user["id"], "test", token_hash(user["token"])),
            )
            if balance is not None:
                conn.execute(
                    "INSERT INTO wallets (id, user_id, balance_paise) VALUES (%s, %s, %s)",
                    (user["wallet_id"], user["id"], balance),
                )
        return user

    return create
