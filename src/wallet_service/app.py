import re
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from psycopg_pool import PoolTimeout

from wallet_service.config import Settings
from wallet_service.db import make_pool, token_hash
from wallet_service.models import DomainError, TransferRequest, TransferResponse, WalletResponse
from wallet_service.observability import Metrics, correlation_id, event
from wallet_service.service import WalletService

bearer = HTTPBearer(auto_error=False)


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    pool = make_pool(settings)
    service = WalletService(pool, settings)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app):
        pool.open(wait=True, timeout=20)
        yield
        pool.close()

    app = FastAPI(title="Wallet & P2P Transfer API", version="1.0.0", lifespan=lifespan)
    app.state.pool = pool
    app.state.service = service
    app.state.metrics = metrics

    @app.middleware("http")
    async def observe(request: Request, call_next):
        supplied = request.headers.get("X-Correlation-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else str(uuid4())
        token = correlation_id.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                event("request_failed", error_type=type(exc).__name__)
                response = JSONResponse(
                    {"error": {"code": "internal_error", "message": "Unexpected server error"}},
                    status_code=500,
                )
            route = getattr(request.scope.get("route"), "path", "unmatched")
            elapsed = time.perf_counter() - start
            metrics.requests.labels(request.method, route, str(response.status_code)).inc()
            metrics.latency.labels(request.method, route).observe(elapsed)
            event(
                "request_completed",
                method=request.method,
                route=route,
                status=response.status_code,
                duration_ms=round(elapsed * 1000, 3),
            )
            response.headers["X-Correlation-ID"] = request_id
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            correlation_id.reset(token)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        if exc.code == "idempotency_conflict":
            metrics.conflicts.inc()
            event("idempotency_conflict")
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed",
                    "fields": [
                        {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
                        for e in exc.errors()
                    ],
                }
            },
            status_code=422,
        )

    async def database_error(request, exc):
        event("database_unavailable", error_type=type(exc).__name__)
        return JSONResponse(
            {
                "error": {
                    "code": "temporarily_unavailable",
                    "message": "Retry later using the same idempotency key; outcome may be unknown",
                }
            },
            status_code=503,
            headers={"Retry-After": "1"},
        )

    for error_type in (
        psycopg.OperationalError,
        psycopg.InterfaceError,
        PoolTimeout,
        psycopg.errors.QueryCanceled,
        psycopg.errors.LockNotAvailable,
    ):
        app.add_exception_handler(error_type, database_error)

    def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> UUID:
        if not credentials or len(credentials.credentials) > 256:
            raise DomainError(401, "unauthorized", "Valid bearer token required")
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE token_hash = %s", (token_hash(credentials.credentials),)
            ).fetchone()
        if not row:
            raise DomainError(401, "unauthorized", "Valid bearer token required")
        return row["id"]

    User = Annotated[UUID, Depends(current_user)]

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "wallet-service", "docs": "/docs", "health": "/health/ready"}

    @app.get("/health/live", tags=["Operations"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Operations"])
    def ready():
        with pool.connection() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '2s'")
            conn.execute("SELECT name FROM schema_migrations LIMIT 1")
        return {"status": "ready"}

    @app.get("/metrics", tags=["Operations"])
    def prometheus():
        return Response(
            generate_latest(metrics.registry), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    @app.post("/wallets", response_model=WalletResponse, tags=["Wallets"])
    def create_wallet(user_id: User):
        result = service.get_or_create_wallet(user_id)
        event("wallet_get_or_create", wallet_id=result["id"])
        return result

    @app.get("/wallets/{wallet_id}", response_model=WalletResponse, tags=["Wallets"])
    def get_wallet(wallet_id: UUID, user_id: User):
        return service.get_wallet(wallet_id, user_id)

    @app.post("/transfers", response_model=TransferResponse, tags=["Transfers"])
    def create_transfer(body: TransferRequest, user_id: User):
        outcome = service.transfer(user_id, body)
        fields = {"transfer_id": outcome.body["id"], "amount_paise": body.amount_paise}
        if outcome.replay:
            metrics.replays.inc()
            event("idempotent_replay_hit", **fields)
        else:
            metrics.created.inc()
            event("transfer_created", status=outcome.body["status"], **fields)
            if outcome.body["status"] == "declined":
                metrics.declined.labels(outcome.body["reason"]).inc()
                event("transfer_declined", reason=outcome.body["reason"], **fields)
            else:
                metrics.succeeded.inc()
                event("wallet_debited", wallet_id=body.from_wallet, **fields)
                event("wallet_credited", wallet_id=body.to_wallet, **fields)
        return outcome.body

    @app.get("/transfers/{transfer_id}", response_model=TransferResponse, tags=["Transfers"])
    def get_transfer(transfer_id: UUID, user_id: User):
        return service.get_transfer(transfer_id, user_id)

    return app
