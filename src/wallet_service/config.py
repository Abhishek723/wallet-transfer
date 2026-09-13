import os
from dataclasses import dataclass

MAX_PAISE = 9_007_199_254_740_991


@dataclass(frozen=True)
class Settings:
    database_url: str
    pool_size: int = 10
    pool_timeout: float = 10
    lock_timeout_ms: int = 10000
    statement_timeout_ms: int = 15000

    @classmethod
    def from_env(cls):
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(
            database_url=url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            pool_timeout=float(os.getenv("DB_POOL_TIMEOUT", "10")),
            lock_timeout_ms=int(os.getenv("DB_LOCK_TIMEOUT_MS", "10000")),
            statement_timeout_ms=int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000")),
        )
