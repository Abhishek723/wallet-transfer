#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose run --rm tools demo-burst --base-url http://app:8000 --output "/demo/$(date +%s)-$$.json"
