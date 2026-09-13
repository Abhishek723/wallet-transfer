# Deploy to Render and Neon

## Create the database

1. Create a free Neon account at <https://console.neon.tech/signup>.
2. Create a PostgreSQL project named `wallet-transfer`; use PostgreSQL 17 and choose
   a region near the Render service.
3. Use **Connect** to obtain a PostgreSQL connection string. Preserve its TLS options.
   A direct connection works for this small bounded pool and for the setup command.
   Keep the URL private. Do not put it in source code, screenshots, or issue comments.

## Publish and deploy the service

1. Publish this application directory as its own GitHub repository.
2. Create a free Render account at <https://dashboard.render.com/register>.
3. Choose **New > Web Service**, select the public repository (or public Git URL),
   and choose the **Docker** runtime and **Free** instance.
4. Set `DATABASE_URL` to the Neon connection string and `DB_POOL_SIZE` to `5`.
5. Set the health-check path to `/health/ready`. Deploy the service. The image's
   `wallet serve` command applies migrations before starting; no paid pre-deploy
   job is required. `render.yaml` contains equivalent settings.
6. Verify `/health/ready`, `/docs`, and `/metrics` at the assigned HTTPS URL.

Render builds from the Dockerfile, which supports the provider's runtime architecture.
For a manually published image, build Linux amd64 explicitly on Apple Silicon.

## Prove deployed behavior

With the virtual environment activated, set `DATABASE_URL` locally to the same Neon
database using a private shell input or local secret manager, then run:

```sh
wallet demo-burst --base-url https://YOUR-SERVICE.onrender.com
```

This creates isolated demo identities and a new treasury before running the probes.
The burst waits up to three minutes for readiness to accommodate cold starts. Keep
its credential file private. Additional runs using that file can spend the remaining
treasury funds; use a fresh setup for an independent test run.

Record Render's log stream while the burst runs, including the public service URL
and correlation IDs. Show a successful transfer, a decline, and a replay. Keep
environment settings and credentials out of the recording. Restart the service,
retry a known completed transfer with the same key, and verify the result and balances
remain unchanged. Metrics resetting across restart is expected.

## Free-tier limits

Render Free sleeps after 15 minutes of inactivity; startup may take about a minute.
Its own free PostgreSQL expires after 30 days, so this setup uses Neon instead.
Neon advertises a free plan without a credit card or time limit. Accounts, region
availability, usage quotas, and any verification prompts must be checked at signup.
Render also limits free outbound traffic, including external database traffic.

Official sources: [Render free limits](https://render.com/docs/free),
[Render Docker](https://render.com/docs/docker), [Neon pricing](https://neon.com/pricing).

## Submission

Provide the GitHub URL, deployed API URL, log recording link, burst command and privately
shared demo credentials, plus `docs/DESIGN.md`. Record actual verification results in
`docs/VERIFICATION.md`. Do not claim a public deploy until the live probes pass.
