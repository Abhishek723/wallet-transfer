import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from prometheus_client import CollectorRegistry, Counter, Histogram

correlation_id = ContextVar("correlation_id", default="startup")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", record.getMessage()),
            "correlation_id": correlation_id.get(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(entry, default=str, separators=(",", ":"))


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def event(name: str, **fields):
    logging.getLogger("wallet").info(name, extra={"event": name, "fields": fields})


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "wallet_http_requests_total",
            "Completed HTTP requests",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "wallet_http_request_duration_seconds",
            "HTTP request duration",
            ["method", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30),
            registry=self.registry,
        )
        self.created = Counter(
            "wallet_transfers_created_total",
            "Committed transfer decisions",
            registry=self.registry,
        )
        self.succeeded = Counter(
            "wallet_transfers_succeeded_total",
            "Committed successful transfers",
            registry=self.registry,
        )
        self.declined = Counter(
            "wallet_transfers_declined_total",
            "Committed declines",
            ["reason"],
            registry=self.registry,
        )
        self.replays = Counter(
            "wallet_idempotent_replays_total",
            "Served idempotent replays",
            registry=self.registry,
        )
        self.conflicts = Counter(
            "wallet_idempotency_conflicts_total",
            "Same key with different request",
            registry=self.registry,
        )
        for reason in ("insufficient_funds", "balance_limit_exceeded"):
            self.declined.labels(reason)
