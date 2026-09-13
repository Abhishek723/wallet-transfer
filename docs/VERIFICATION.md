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
The live API is <https://wallet-transfer-p325.onrender.com>.
Render Free and Neon Free (PostgreSQL 17) run in Singapore. Initial deployed commit:
`3859cd763c1efcde0435a56048c1e1a76af8b314`, September 13, 2026.

- Root, `/docs`, `/openapi.json`, `/health/live`, `/health/ready`, `/metrics`: HTTP 200.
- Concurrent get-or-create: **50 requests, one wallet**.
- Same-key retry storm: **30 requests, one transfer**, identical responses.
- Conflicting replay: **409**; persisted decline replay passed.
- Contention: **400 requests, 361 succeeded, 39 declined, zero HTTP 5xx**.
- Total balance: **10,000,000 paise before and after**; minimum **7,102 paise**.
- Actual Render restart at approximately 09:19 UTC: saved transfer
  `cf52e7a2-2e1c-4e89-92b7-25cb10850cc5` replayed with identical response and
  unchanged balances. Render's Events view confirmed the restart.

The deployed burst ran at approximately 09:17-09:18 UTC with correlation prefix
`burst-72007c9c-1aa3-4459-bcc1-cdff4dfa4669`.
Repeat using the privately supplied credential file:

```sh
wallet burst --config .demo/render-reviewer.json
```

For fresh identities and a new treasury, an operator with database access can run
`wallet demo-burst --base-url https://wallet-transfer-p325.onrender.com`.
Do not publish the credential file or database URL. These are fake-money tests.

## Deployed log evidence

[Public JSON log excerpt](deployed-logs.jsonl) contains actual events observed in
Render during the deployed burst, including a matched debit/credit pair, a decline,
a replay, and a conflict. It is a selected static excerpt, not a full log archive
or a streaming recording. No tokens or database credentials are included.
The [Render live logs](https://dashboard.render.com/web/srv-daj6jom7bikc73atldt0/logs)
require the owner's Render login. A screen recording of the live stream has not
been captured; capture one for submission if the reviewer requires streaming evidence.
