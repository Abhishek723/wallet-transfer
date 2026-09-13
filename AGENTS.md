# Repository Guidelines

## Structure

`src/wallet_service/` contains the FastAPI application, explicit SQL service,
configuration, observability, CLI, and versioned SQL migrations. `tests/` runs against
real PostgreSQL. `scripts/burst.sh` exercises the HTTP service. `docs/` contains
design, deployment, and observation instructions.

## Development

Install `requirements-dev.txt` and then `pip install --no-deps -e .` in a virtual
environment. Use `docker compose up --build -d --wait` to start the service and database.
Run `ruff check .`, `ruff format --check .`, and `pytest -q` with `TEST_DATABASE_URL`
pointing at a disposable database. Each test owns a temporary schema.

## Style and correctness

Use four-space indentation, type hints, snake_case functions, and Ruff formatting.
Keep SQL parameterized. Money must remain integer paise. Keep idempotency decisions,
both balance updates, and transfer status in one transaction. Acquire wallet locks
in ascending UUID order with `FOR NO KEY UPDATE`. Do not introduce process-local
locks or cached balances as correctness mechanisms. Log successful domain events
only after commit. Add a new SQL migration instead of editing an applied one.

## Tests and changes

Tests are named `test_*.py`; changes to money movement need real-database concurrency,
rollback, replay, and conservation tests. Keep runtime and development lock files
consistent with `pyproject.toml`. Use concise imperative commit messages describing
actual changes. Pull requests should explain behavior and report verification.

## Secrets and publication

Never commit `.env`, `.demo/`, database credentials, or bearer tokens. Keep request
bodies and credentials out of logs. Document AI involvement honestly. Publish only
this application directory, and report local versus deployed verification separately.
