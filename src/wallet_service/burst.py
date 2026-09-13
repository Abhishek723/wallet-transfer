import asyncio
import json
import random
import time
from uuid import uuid4

import httpx

from wallet_service.config import MAX_PAISE


def require(condition: bool, message: str):
    if not condition:
        raise RuntimeError(message)


async def run_burst(config: dict, base_url: str | None = None, count: int = 400):
    users = config["users"]
    treasury = config["treasury"]
    run = str(uuid4())
    semaphore = asyncio.Semaphore(50)
    async with httpx.AsyncClient(
        base_url=(base_url or config["base_url"]).rstrip("/"),
        timeout=60,
        limits=httpx.Limits(max_connections=60),
    ) as client:
        deadline = time.monotonic() + 180
        while True:
            try:
                ready = await client.get("/health/ready")
                if ready.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            require(time.monotonic() < deadline, "Service did not become ready in 180 seconds")
            await asyncio.sleep(2)

        async def call(method, path, user, body=None, expected=200):
            async with semaphore:
                response = await client.request(
                    method,
                    path,
                    headers={
                        "Authorization": f"Bearer {user['token']}",
                        "X-Correlation-ID": f"burst-{run}-{uuid4()}",
                    },
                    **({"json": body} if body is not None else {}),
                )
            require(
                response.status_code == expected,
                f"{method} {path}: expected {expected}, got {response.status_code}: "
                f"{response.text[:300]}",
            )
            return response.json()

        wallets = await asyncio.gather(*[call("POST", "/wallets", users[0]) for _ in range(50)])
        require(len({w["id"] for w in wallets}) == 1, "Get-or-create returned multiple wallets")
        wallet_ids = [wallets[0]["id"]]
        for user in users[1:]:
            wallet_ids.append((await call("POST", "/wallets", user))["id"])
        print(
            json.dumps(
                {
                    "probe": "concurrent_get_or_create",
                    "requests": 50,
                    "distinct_wallets": 1,
                    "passed": True,
                }
            ),
            flush=True,
        )

        for wallet_id in wallet_ids:
            result = await call(
                "POST",
                "/transfers",
                treasury,
                {
                    "from": treasury["wallet_id"],
                    "to": wallet_id,
                    "amount_paise": 100_000,
                    "idempotency_key": f"fund-{run}-{wallet_id}",
                },
            )
            require(result["status"] == "succeeded", "Treasury has insufficient demo funds")

        async def balances():
            pairs = list(zip(users, wallet_ids, strict=True)) + [(treasury, treasury["wallet_id"])]
            return [
                (await call("GET", f"/wallets/{wid}", user))["balance_paise"] for user, wid in pairs
            ]

        before = await balances()
        body = {
            "from": wallet_ids[0],
            "to": wallet_ids[1],
            "amount_paise": 1000,
            "idempotency_key": f"storm-{run}",
        }
        replies = await asyncio.gather(
            *[call("POST", "/transfers", users[0], body) for _ in range(30)]
        )
        require(all(r == replies[0] for r in replies), "Replay responses differ")
        require(replies[0]["status"] == "succeeded", "Retry storm transfer declined")
        after = await balances()
        require(
            after[0] == before[0] - 1000 and after[1] == before[1] + 1000,
            "Retry storm applied an incorrect balance change",
        )
        require(sum(before) == sum(after), "Retry storm broke conservation")
        await call("POST", "/transfers", users[0], {**body, "amount_paise": 1001}, expected=409)
        print(
            json.dumps(
                {
                    "probe": "idempotent_retry_storm",
                    "requests": 30,
                    "distinct_transfers": len({r["id"] for r in replies}),
                    "conflict_status": 409,
                    "passed": True,
                }
            ),
            flush=True,
        )

        declined_body = {**body, "amount_paise": MAX_PAISE, "idempotency_key": f"decline-{run}"}
        declined = await call("POST", "/transfers", users[0], declined_body)
        require(
            declined["status"] == "declined" and declined["reason"] == "insufficient_funds",
            "Overdraft did not decline cleanly",
        )
        require(
            await call("POST", "/transfers", users[0], declined_body) == declined,
            "Declined transfer replay changed",
        )

        rng = random.Random(42)
        jobs = []
        for i in range(count):
            sender, recipient = (
                (0, 1) if i % 4 == 0 else (1, 0) if i % 4 == 1 else rng.sample(range(len(users)), 2)
            )
            jobs.append((sender, recipient, rng.randint(1, 50_000), f"contention-{run}-{i}"))
        outcomes = await asyncio.gather(
            *[
                call(
                    "POST",
                    "/transfers",
                    users[sender],
                    {
                        "from": wallet_ids[sender],
                        "to": wallet_ids[recipient],
                        "amount_paise": amount,
                        "idempotency_key": key,
                    },
                )
                for sender, recipient, amount, key in jobs
            ]
        )
        final = await balances()
        require(sum(final) == sum(before), "Contention created or destroyed money")
        require(min(final) >= 0, "A wallet went negative")
        expected_balances = after[:]
        for (sender, recipient, amount, _), outcome in zip(jobs, outcomes, strict=True):
            if outcome["status"] == "succeeded":
                expected_balances[sender] -= amount
                expected_balances[recipient] += amount
            else:
                require(outcome["status"] == "declined", "Unexpected transfer status")
        require(final == expected_balances, "Balances do not reconcile with transfer responses")
        summary = {
            "probe": "conservation_under_contention",
            "requests": count,
            "succeeded": sum(r["status"] == "succeeded" for r in outcomes),
            "declined": sum(r["status"] == "declined" for r in outcomes),
            "total_before_paise": sum(before),
            "total_after_paise": sum(final),
            "minimum_balance_paise": min(final),
            "http_5xx": 0,
            "passed": True,
        }
        print(json.dumps(summary), flush=True)
        return summary
