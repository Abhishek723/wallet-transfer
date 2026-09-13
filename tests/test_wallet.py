import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from wallet_service.app import create_app
from wallet_service.config import MAX_PAISE
from wallet_service.db import migrate
from wallet_service.observability import JsonFormatter


def transfer(a, b, amount=100, key=None):
    return {
        "from": str(a["wallet_id"]),
        "to": str(b["wallet_id"]),
        "amount_paise": amount,
        "idempotency_key": key or str(uuid4()),
    }


def balances(settings):
    with psycopg.connect(settings.database_url) as conn:
        return dict(conn.execute("SELECT id, balance_paise FROM wallets").fetchall())


def transfer_count(settings):
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT count(*) FROM transfers").fetchone()[0]


def test_concurrent_wallet_creation(client, user_factory, settings):
    user = user_factory()
    with ThreadPoolExecutor(max_workers=50) as executor:
        responses = list(
            executor.map(lambda _: client.post("/wallets", headers=user["headers"]), range(50))
        )
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["id"] for r in responses}) == 1
    with psycopg.connect(settings.database_url) as conn:
        assert (
            conn.execute("SELECT count(*) FROM wallets WHERE user_id=%s", (user["id"],)).fetchone()[
                0
            ]
            == 1
        )


def test_retry_storm_across_instances(client, settings, user_factory):
    a, b = user_factory(1000), user_factory(0)
    body = transfer(a, b, 100)
    with TestClient(create_app(settings)) as second, ThreadPoolExecutor(max_workers=30) as executor:
        responses = list(
            executor.map(
                lambda i: (client if i % 2 else second).post(
                    "/transfers", json=body, headers=a["headers"]
                ),
                range(30),
            )
        )
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)
    assert balances(settings) == {a["wallet_id"]: 900, b["wallet_id"]: 100}
    assert transfer_count(settings) == 1


def test_concurrent_conflicting_payloads(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(0)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(
            executor.map(
                lambda i: client.post(
                    "/transfers", json=transfer(a, b, 100 + i % 2, key), headers=a["headers"]
                ),
                range(20),
            )
        )
    assert sum(r.status_code == 200 for r in responses) == 10
    assert sum(r.status_code == 409 for r in responses) == 10
    assert transfer_count(settings) == 1
    assert sum(balances(settings).values()) == 1000


def test_conservation_and_reconciliation(client, user_factory, settings):
    users = [user_factory(1000) for _ in range(4)]
    rng = random.Random(42)
    jobs = []
    for i in range(300):
        a, b = (0, 1) if i % 4 == 0 else (1, 0) if i % 4 == 1 else rng.sample(range(4), 2)
        jobs.append((a, b, rng.randint(1, 1500)))
    with ThreadPoolExecutor(max_workers=40) as executor:
        responses = list(
            executor.map(
                lambda job: client.post(
                    "/transfers",
                    json=transfer(users[job[0]], users[job[1]], job[2]),
                    headers=users[job[0]]["headers"],
                ),
                jobs,
            )
        )
    expected = {u["wallet_id"]: 1000 for u in users}
    assert all(r.status_code == 200 for r in responses)
    for (a, b, amount), response in zip(jobs, responses, strict=True):
        if response.json()["status"] == "succeeded":
            expected[users[a]["wallet_id"]] -= amount
            expected[users[b]["wallet_id"]] += amount
    final = balances(settings)
    assert final == expected
    assert sum(final.values()) == 4000
    assert min(final.values()) >= 0
    assert transfer_count(settings) == 300
    with psycopg.connect(settings.database_url) as conn:
        assert (
            conn.execute("SELECT count(*) FROM transfers WHERE status='pending'").fetchone()[0] == 0
        )


def test_decline_is_replayed_after_funding(client, user_factory, settings):
    a, b, funder = user_factory(0), user_factory(0), user_factory(1000)
    body = transfer(a, b)
    original = client.post("/transfers", json=body, headers=a["headers"])
    assert original.json()["reason"] == "insufficient_funds"
    assert (
        client.post("/transfers", json=transfer(funder, a, 500), headers=funder["headers"]).json()[
            "status"
        ]
        == "succeeded"
    )
    assert client.post("/transfers", json=body, headers=a["headers"]).json() == original.json()
    assert balances(settings)[a["wallet_id"]] == 500


def test_authorization(client, user_factory):
    a, b, outsider = user_factory(1000), user_factory(0), user_factory(0)
    assert client.post("/wallets").status_code == 401
    assert client.post("/wallets", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get(f"/wallets/{a['wallet_id']}", headers=b["headers"]).status_code == 404
    assert client.post("/transfers", json=transfer(a, b), headers=b["headers"]).status_code == 403
    result = client.post("/transfers", json=transfer(a, b), headers=a["headers"]).json()
    for user in (a, b):
        assert client.get(f"/transfers/{result['id']}", headers=user["headers"]).json() == result
    assert client.get(f"/transfers/{result['id']}", headers=outsider["headers"]).status_code == 404


@pytest.mark.parametrize("amount", [0, -1, 1.5, 1.0, True, False, "100", None, MAX_PAISE + 1])
def test_invalid_money(client, user_factory, settings, amount):
    a, b = user_factory(1000), user_factory(0)
    assert (
        client.post("/transfers", json=transfer(a, b, amount), headers=a["headers"]).status_code
        == 422
    )
    assert transfer_count(settings) == 0


def test_invalid_input_and_missing_wallet(client, user_factory):
    a, b = user_factory(1000), user_factory(0)
    for body in (
        transfer(a, a),
        {**transfer(a, b), "extra": 1},
        transfer(a, b, key=" "),
        transfer(a, b, key="x" * 129),
    ):
        assert client.post("/transfers", json=body, headers=a["headers"]).status_code == 422
    assert (
        client.post(
            "/transfers",
            content="{bad",
            headers={**a["headers"], "Content-Type": "application/json"},
        ).status_code
        == 422
    )
    body = {**transfer(a, b), "to": str(uuid4())}
    assert client.post("/transfers", json=body, headers=a["headers"]).status_code == 404


def test_key_scope_is_per_user(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(1000)
    for sender, recipient in ((a, b), (b, a)):
        assert (
            client.post(
                "/transfers",
                json=transfer(sender, recipient, key="same-key"),
                headers=sender["headers"],
            ).json()["status"]
            == "succeeded"
        )
    assert transfer_count(settings) == 2


def test_credit_overflow_declines(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(MAX_PAISE)
    before = balances(settings)
    result = client.post("/transfers", json=transfer(a, b), headers=a["headers"])
    assert result.json()["reason"] == "balance_limit_exceeded"
    assert balances(settings) == before


def test_failure_after_debit_rolls_back_and_key_can_retry(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(0)
    body = transfer(a, b)
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("""CREATE FUNCTION fail_credit() RETURNS trigger AS $$
            BEGIN IF NEW.balance_paise > OLD.balance_paise THEN
                RAISE EXCEPTION 'injected credit failure'; END IF; RETURN NEW; END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER injected BEFORE UPDATE ON wallets
            FOR EACH ROW EXECUTE FUNCTION fail_credit();""")
    assert client.post("/transfers", json=body, headers=a["headers"]).status_code == 500
    assert balances(settings) == {a["wallet_id"]: 1000, b["wallet_id"]: 0}
    assert transfer_count(settings) == 0
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("DROP TRIGGER injected ON wallets")
    assert (
        client.post("/transfers", json=body, headers=a["headers"]).json()["status"] == "succeeded"
    )


def test_lost_response_and_restart_replays(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(0)
    body = transfer(a, b)
    # Discard the first response as if the network dropped it after commit.
    client.post("/transfers", json=body, headers=a["headers"])
    with TestClient(create_app(settings)) as restarted:
        result = restarted.post("/transfers", json=body, headers=a["headers"])
        assert result.json()["status"] == "succeeded"
    assert transfer_count(settings) == 1
    assert balances(settings)[a["wallet_id"]] == 900


def test_lock_timeout_rolls_back(client, user_factory, settings):
    a, b = user_factory(1000), user_factory(0)
    body = transfer(a, b)
    with TestClient(create_app(replace(settings, lock_timeout_ms=50))) as impatient:
        with psycopg.connect(settings.database_url) as blocker:
            blocker.execute(
                "SELECT id FROM wallets WHERE id=%s FOR NO KEY UPDATE", (a["wallet_id"],)
            )
            response = impatient.post("/transfers", json=body, headers=a["headers"])
            assert response.status_code == 503
            assert response.headers["Retry-After"] == "1"
    assert transfer_count(settings) == 0
    assert (
        client.post("/transfers", json=body, headers=a["headers"]).json()["status"] == "succeeded"
    )


def test_observability(client, user_factory, caplog):
    caplog.set_level(logging.INFO, logger="wallet")
    a, b = user_factory(1000), user_factory(0)
    body = transfer(a, b)
    for _ in range(2):
        response = client.post(
            "/transfers", json=body, headers={**a["headers"], "X-Correlation-ID": "test-observe"}
        )
        assert response.headers["X-Correlation-ID"] == "test-observe"
    client.post("/transfers", json=transfer(a, b, 2000), headers=a["headers"])
    events = [getattr(r, "event", None) for r in caplog.records]
    assert events.count("wallet_debited") == 1
    assert events.count("wallet_credited") == 1
    assert "idempotent_replay_hit" in events
    assert "transfer_declined" in events
    assert a["token"] not in caplog.text
    exposition = client.get("/metrics").text
    assert "wallet_transfers_created_total 2.0" in exposition
    assert "wallet_idempotent_replays_total 1.0" in exposition
    assert "wallet_http_request_duration_seconds_bucket" in exposition
    assert 'route="/transfers"' in exposition
    formatter = JsonFormatter()
    assert json.loads(formatter.format(caplog.records[0]))["event"]
    assert client.get("/health/ready").status_code == 200
    assert client.get("/health/live").status_code == 200


def test_migrations_repeat_safely(settings):
    migrate(settings.database_url)
    with psycopg.connect(settings.database_url) as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1


def test_database_blocks_negative_balance(settings, user_factory):
    a = user_factory(0)
    with psycopg.connect(settings.database_url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE wallets SET balance_paise=-1 WHERE id=%s", (a["wallet_id"],))
