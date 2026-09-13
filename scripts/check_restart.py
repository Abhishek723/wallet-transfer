"""Verify replay after an actual local Compose app restart."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path, required=True)
args = parser.parse_args()
config = json.loads(args.config.read_text())
if urlparse(config["base_url"]).hostname not in ("localhost", "127.0.0.1"):
    raise SystemExit("This script restarts only the local Compose app; use a local demo config.")
user, other = config["users"][:2]

with httpx.Client(base_url=config["base_url"], timeout=20) as client:
    headers = {"Authorization": f"Bearer {user['token']}"}
    other_headers = {"Authorization": f"Bearer {other['token']}"}
    a = client.post("/wallets", headers=headers).json()["id"]
    b = client.post("/wallets", headers=other_headers).json()["id"]
    body = {"from": a, "to": b, "amount_paise": 1, "idempotency_key": f"restart-{uuid4()}"}
    original = client.post("/transfers", json=body, headers=headers)
    original.raise_for_status()
    before = [
        client.get(f"/wallets/{a}", headers=headers).json(),
        client.get(f"/wallets/{b}", headers=other_headers).json(),
    ]
    subprocess.run(["docker", "compose", "restart", "app"], check=True)
    deadline = time.monotonic() + 60
    while True:
        try:
            if client.get("/health/ready").status_code == 200:
                break
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            raise SystemExit("App did not recover after restart")
        time.sleep(1)
    replay = client.post("/transfers", json=body, headers=headers)
    after = [
        client.get(f"/wallets/{a}", headers=headers).json(),
        client.get(f"/wallets/{b}", headers=other_headers).json(),
    ]
    if (
        replay.status_code != original.status_code
        or replay.json() != original.json()
        or before != after
    ):
        raise SystemExit("FAIL: restart replay changed the result or balances")
    print(
        json.dumps(
            {
                "probe": "actual_container_restart",
                "same_response": True,
                "balances_unchanged": True,
                "passed": True,
            }
        )
    )
