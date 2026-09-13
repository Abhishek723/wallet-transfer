import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import uvicorn

from wallet_service.burst import run_burst
from wallet_service.config import Settings
from wallet_service.db import migrate
from wallet_service.demo import provision
from wallet_service.observability import configure_logging, event


def dispatch():
    parser = argparse.ArgumentParser(description="Wallet service operations")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Apply migrations and start the API")
    commands.add_parser("migrate", help="Apply checked-in SQL migrations")
    for name in ("demo", "demo-burst"):
        command = commands.add_parser(name, help="Create fresh demo users and a funded treasury")
        command.add_argument("--output", type=Path)
        command.add_argument("--base-url", default="http://localhost:8000")
    burst = commands.add_parser(
        "burst", help="Run all concurrency probes using existing credentials"
    )
    burst.add_argument("--config", type=Path, required=True)
    burst.add_argument("--base-url")
    burst.add_argument("--count", type=int, default=400)
    args = parser.parse_args()
    if args.command == "serve":
        configure_logging()
        settings = Settings.from_env()
        migrate(settings.database_url)
        event("migrations_applied")
        uvicorn.run(
            "wallet_service.app:create_app",
            factory=True,
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8000")),
            log_config=None,
            access_log=False,
        )
    elif args.command == "migrate":
        migrate(Settings.from_env().database_url)
        print("Migrations applied")
    elif args.command in ("demo", "demo-burst"):
        settings = Settings.from_env()
        migrate(settings.database_url)
        output = args.output or Path(".demo") / f"{uuid4()}.json"
        config = provision(settings.database_url, output, args.base_url)
        print(f"Demo credentials stored in {output}; treat this file as a secret.", flush=True)
        if args.command == "demo-burst":
            asyncio.run(run_burst(config))
    else:
        if not 1 <= args.count <= 10000:
            parser.error("--count must be between 1 and 10000")
        asyncio.run(run_burst(json.loads(args.config.read_text()), args.base_url, args.count))


def main():
    try:
        dispatch()
    except Exception as exc:
        # Connection exceptions may include credentials; report only their type here.
        print(
            f"Command failed ({type(exc).__name__}). Check configuration and service logs.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
