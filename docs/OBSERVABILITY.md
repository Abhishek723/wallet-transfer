# Logs and metrics

## Logs

```sh
docker compose logs -f --no-log-prefix app
```

Every request has `X-Correlation-ID` (accept a bounded safe value or generate one).
JSON entries include timestamp, level, event, correlation ID, and relevant transfer
or wallet IDs. Domain events: `transfer_created`, `wallet_debited`, `wallet_credited`,
`transfer_declined`, `idempotent_replay_hit`, and `idempotency_conflict`.
Domain success logs occur after commit; a process crash between commit and logging
can lose an event. Database records are authoritative. Tokens, request bodies, and
database URLs are not logged by the application.

## Prometheus

Scrape `/metrics` every 15 seconds. Request labels use route templates, not wallet
IDs or idempotency keys. The following queries work in Prometheus or Grafana:

```promql
# Request rate, excluding operational probes
sum(rate(wallet_http_requests_total{route!~"/metrics|/health/.*"}[5m]))

# p99 latency in seconds for business endpoints
histogram_quantile(0.99,
  sum by (le) (rate(wallet_http_request_duration_seconds_bucket{route!~"/metrics|/health/.*"}[5m])))

# Server error ratio
sum(rate(wallet_http_requests_total{status=~"5.."}[5m]))
  / clamp_min(sum(rate(wallet_http_requests_total[5m])), 0.000001)

# Committed decisions, successful transfers, and insufficient-funds declines
sum(increase(wallet_transfers_created_total[5m]))
sum(increase(wallet_transfers_succeeded_total[5m]))
sum(increase(wallet_transfers_declined_total{reason="insufficient_funds"}[5m]))

# Replays and conflicting key reuse
sum(increase(wallet_idempotent_replays_total[5m]))
sum(increase(wallet_idempotency_conflicts_total[5m]))
```

Histogram p99 is an estimate and requires multiple scrapes over the chosen window.
These counters belong to one process and reset on restart. The supplied deployment
uses one Uvicorn worker per instance. If scaling out, scrape every instance separately
and aggregate; do not scrape a load balancer as if it were a single counter source.

## Recording evidence

Keep a log terminal visible while running `sh scripts/burst.sh` in another terminal.
For deployment evidence use Render's live log view and run the burst against the
public URL. A saved JSON log file is useful for inspection but is not a substitute
for the requested public logs link or recording of deployed behavior.
