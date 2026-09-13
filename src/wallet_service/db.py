import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from wallet_service.config import Settings


def make_pool(settings: Settings):
    return ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=settings.pool_size,
        timeout=settings.pool_timeout,
        open=False,
        check=ConnectionPool.check_connection,
        kwargs={"autocommit": True, "row_factory": dict_row, "connect_timeout": 10},
    )


def migrate(database_url: str):
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(873429105)")
            conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY, checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                content = path.read_text()
                checksum = hashlib.sha256(content.encode()).hexdigest()
                existing = conn.execute(
                    "SELECT checksum FROM schema_migrations WHERE name = %s", (path.name,)
                ).fetchone()
                if existing:
                    if existing[0] != checksum:
                        raise RuntimeError(f"Applied migration changed: {path.name}")
                    continue
                conn.execute(content)
                conn.execute(
                    "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
