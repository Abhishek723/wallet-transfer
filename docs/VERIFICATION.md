# Verification evidence

## Local and CI verification, September 13, 2026

- Real PostgreSQL integration suite: **24 passed**.
- Ruff lint and formatting: passed.
- Multi-stage Docker build and Compose startup: passed; app and database healthy.
- Application user: UID/GID **10001**, not root.
- Concurrent wallet creation: **50 requests, one wallet**.
- Idempotent retry storm: **30 requests, one transfer**, identical responses.
- Different amount with the same key: **409**.
- Contention run: **400 requests, 343 succeeded, 57 declined, zero HTTP 5xx**.
- Total test balance: **10,000,000 paise before and after**.
- Minimum ending wallet balance: **11,357 paise**, none negative.
- A separate host-side HTTP burst also passed (358 successes, 42 declines).
- Actual Docker app restart: the same key returned the original response and
  balances remained unchanged (`scripts/check_restart.py`).

The split between successes and declines depends on concurrent scheduling. The
assertions check conservation and reconcile every success to actual balances;
they do not require a particular success count under contention.

[GitHub CI run](https://github.com/Abhishek723/wallet-transfer/actions/runs/34748060851)
passed on a clean Ubuntu runner with Python 3.12, real PostgreSQL, the Docker build,
and the burst script. Its logs contain the request and domain JSON events from the
CI container. These are CI logs, not logs from a publicly deployed API.

## Public deployment

The source is published at <https://github.com/Abhishek723/wallet-transfer>.
Render and Neon account setup is pending. A live API URL, deployed burst result,
and deployed log recording have **not** yet been verified. Do not present the local
URL or CI container as the public deployment.
