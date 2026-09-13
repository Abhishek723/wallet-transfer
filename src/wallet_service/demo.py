import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

import psycopg

from wallet_service.db import token_hash


def provision(database_url: str, output: Path, base_url: str):
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally replacing credentials for an earlier run.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    run_id = str(uuid4())
    users = [
        {"id": str(uuid4()), "token": secrets.token_urlsafe(32), "name": f"demo-{run_id}-{i}"}
        for i in range(5)
    ]
    treasury = {
        "id": str(uuid4()),
        "token": secrets.token_urlsafe(32),
        "wallet_id": str(uuid4()),
        "name": f"treasury-{run_id}",
    }
    config = {"run_id": run_id, "base_url": base_url, "users": users, "treasury": treasury}
    try:
        with os.fdopen(fd, "w") as file:
            with psycopg.connect(database_url, connect_timeout=10) as conn:
                for user in [treasury, *users]:
                    conn.execute(
                        "INSERT INTO users (id, name, token_hash) VALUES (%s, %s, %s)",
                        (user["id"], user["name"], token_hash(user["token"])),
                    )
                conn.execute(
                    "INSERT INTO wallets (id, user_id, balance_paise) VALUES (%s, %s, %s)",
                    (treasury["wallet_id"], treasury["id"], 10_000_000),
                )
                json.dump(config, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return config
