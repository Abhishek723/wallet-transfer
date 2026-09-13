# Wallet & P2P Transfer

A Python/FastAPI service with PostgreSQL transactions, per-user idempotency,
structured JSON logs, and Prometheus metrics. All money uses integer paise.

## Live deployment

- API and interactive docs: <https://wallet-transfer-p325.onrender.com/docs>
- Readiness: <https://wallet-transfer-p325.onrender.com/health/ready>
- Metrics: <https://wallet-transfer-p325.onrender.com/metrics>
- [Deployed verification results](docs/VERIFICATION.md)
- [Actual deployed log excerpt](docs/deployed-logs.jsonl) (static, not a live stream)

Hosted on Render Free with Neon PostgreSQL 17, both in Singapore. The free web
service sleeps when inactive; the first request can take about a minute. Demo
credentials are shared privately. No real money or payment accounts are involved.

## Run locally

Requires Docker with Compose:

```sh
docker compose up --build -d --wait
sh scripts/burst.sh
```

API: <http://localhost:8000>. Interactive API docs: <http://localhost:8000/docs>.
Use `APP_PORT=8001 docker compose up --build -d --wait` if port 8000 is occupied.
PostgreSQL is published only on localhost:55432; change `DB_PORT` if necessary.
`docker compose down` stops the services and preserves data.

The burst command creates fresh users and a treasury, performs 50 simultaneous wallet
creations, 30 same-key transfers, a conflicting replay, a persisted decline, and 400
contending transfers. It asserts response equality, exact balance changes,
conservation, nonnegative balances, and reconciliation with successful transfers.
It exits nonzero on failure. Run it when no other workload uses those demo wallets.

## Develop and test

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pip install --no-deps -e .
docker compose up -d db --wait
docker compose exec -T db createdb -U wallet wallet_test  # once
export TEST_DATABASE_URL=postgresql://wallet:wallet@localhost:55432/wallet_test
pytest -q
ruff check .
ruff format --check .
```

Each test creates and drops its own schema in the disposable test database. Tests
exercise real PostgreSQL, including two app instances, conflict races, rollback
after debit, restart replay, lock timeouts, authorization, strict amounts, and
metrics. Set `DATABASE_URL` and run `wallet serve` to develop outside Docker.
The default app uses one Uvicorn worker and a bounded database connection pool.

After creating and funding a local demo, verify an actual container restart with
`python scripts/check_restart.py --config .demo/local-reviewer.json`.
This briefly restarts only the Compose app and checks that retrying a committed
transfer returns the original result without moving balances again.
For a hosted restart, run the command below, restart the service in Render, and
continue only after Render confirms the restart. The script checks the saved
response and balances.

```sh
python scripts/check_restart.py --manual --config .demo/render-reviewer.json
```

## API contract

All four business endpoints require `Authorization: Bearer <token>`.

| Endpoint | Result |
| --- | --- |
| `POST /wallets` | Get or create the caller's zero-balance wallet; `200` |
| `GET /wallets/{id}` | Owner's current `id` and `balance_paise`; `200` |
| `POST /transfers` | Final transfer decision; `200`, including declines |
| `GET /transfers/{id}` | Transfer visible to sender or recipient; `200` |

```json
{
  "from": "11111111-1111-4111-8111-111111111111",
  "to": "22222222-2222-4222-8222-222222222222",
  "amount_paise": 1000,
  "idempotency_key": "payment-001"
}
```

The response contains `id`, `from`, `to`, `amount_paise`, `status` (`succeeded` or
`declined`), `reason`, and `created_at`. Retries return the same HTTP status and
body. Correlation IDs can differ and live in `X-Correlation-ID` response headers.
Keys are scoped to the authenticated user, retained permanently, and accept 1-128
ASCII letters, digits, `.`, `_`, `:`, or `-`. Reusing a key with a different valid
transfer body returns `409`. JSON field order does not matter. A persisted decline
stays declined after funding; submit a new key for a new attempt.

Amounts must be strict integers from 1 through 9,007,199,254,740,991; balances share
that upper bound to remain exact in common JSON clients. Floats, booleans, numeric
strings, self-transfers, extra fields, and invalid identifiers return `422`.
Insufficient funds and recipient overflow decline without any balance change.
Invalid tokens return `401`; unauthorized debits `403`; missing or concealed reads
`404`; transient database failures `503` with `Retry-After: 1`. Retry an uncertain
outcome using the same key. Authentication and validation failures do not reserve keys.

## Demo credentials and remote probes

```sh
# DATABASE_URL points to the target database; never commit it.
wallet demo --base-url https://YOUR-SERVICE.onrender.com --output .demo/reviewer.json
wallet burst --config .demo/reviewer.json
# Or provision and test together:
wallet demo-burst --base-url https://YOUR-SERVICE.onrender.com
```

Setup creates five users with no wallets and a separate treasury containing
10,000,000 test paise. This explicit bootstrap happens before measurement; ordinary
wallets receive funds through transfers. Credentials are random, stored with file
mode 0600, and only token hashes enter PostgreSQL. Existing credential files are
never overwritten. Share a reviewer file privately, never through the public repo.
The standalone burst command needs only that file and HTTP access, not database access.

## Deployment and observation

Follow [Deployment](docs/DEPLOYMENT.md) for Render + Neon and [Observability](docs/OBSERVABILITY.md)
for logs, request rate, p99, errors, and domain counters. The Dockerfile is
multi-stage, runs as UID 10001, and includes a readiness health check. Migrations
run before startup under a database advisory lock and reject edited applied files.

The [one-page design write-up](docs/DESIGN.md) explains correctness, tradeoffs,
failure behavior, AI involvement, and the free-tier target. No real payment rails,
currency conversion, public deposits, or user registration are included.
The submission-ready [single-page PDF](output/pdf/wallet-design.pdf) contains the same write-up.
To regenerate it, install `reportlab` and run `python scripts/build_writeup.py`.
