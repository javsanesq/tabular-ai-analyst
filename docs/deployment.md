# Deployment Runbook

This project is prepared for Fly.io deployment, but the hosted app is not considered live until the smoke checks at the end of this document pass against the public URL.

## Current Fly Primitives

The runbook follows the current Fly.io deployment model:

- `fly deploy` builds and releases the app from `fly.toml`.
- `fly secrets set` stores runtime secrets; Fly does not expose plaintext secret values after setting them.
- Volumes must be created before an app can mount persistent local storage.
- Fly now documents both Managed Postgres through `fly mpg` and unmanaged Postgres through `fly postgres`; this app only needs a reachable `DATABASE_URL`.

References:

- [Fly CLI docs](https://fly.io/docs/flyctl/)
- [Fly deploy docs](https://fly.io/docs/launch/deploy/)
- [Fly secrets docs](https://fly.io/docs/secrets/)
- [Fly volumes docs](https://fly.io/docs/flyctl/volumes/)
- [Fly Postgres docs](https://fly.io/docs/flyctl/postgres/)
- [Fly Managed Postgres docs](https://fly.io/docs/flyctl/mpg/)

## Preflight

```bash
fly version
fly auth whoami
docker compose config
PYTHON=.venv/bin/python make test
PYTHON=.venv/bin/python make benchmark
cd ui && npm run build && npm run test:e2e
```

If `fly` is not installed, install `flyctl` first and run `fly auth login`.

## App Setup

```bash
fly apps create tabular-ai-analyst --org personal
fly volumes create tabular_data --region mad --size 1
```

The mounted volume stores uploaded demo files under `/app/data`. Postgres stores metadata, analysis history, traces, eval runs, and quotas.

## Database

Use one of these database options:

```bash
# Managed Postgres option, if available on your account.
fly mpg create

# Unmanaged Fly Postgres option.
fly postgres create --name tabular-ai-analyst-db --region mad
```

After provisioning, set `DATABASE_URL` as a secret. The final connection string must use the `postgresql+psycopg://...` SQLAlchemy dialect.

## Secrets

```bash
fly secrets set \
  APP_ENV=production \
  LLM_PROVIDER=openai \
  OPENAI_API_KEY=... \
  API_AUTH_TOKEN=... \
  DATABASE_URL=postgresql+psycopg://...
```

Production mode intentionally rejects missing `OPENAI_API_KEY`, missing `API_AUTH_TOKEN`, and mock LLM mode.

## Deploy

```bash
fly deploy
fly status
fly logs
```

The API Docker image runs the FastAPI app and serves `/health/ready` for health checks. The current `fly.toml` deploys the API only; the React workbench is Docker Compose-ready locally and should be deployed separately or folded into the API image before a single public demo URL is announced.

## Hosted Smoke

```bash
BASE_URL=https://tabular-ai-analyst.fly.dev \
API_AUTH_TOKEN=<demo-token> \
scripts/smoke_docker.sh
```

Expected result:

- Readiness returns `{"status":"ready"}`.
- Wine Quality demo dataset loads.
- A governed chart analysis succeeds.
- An unsafe Python/file-access request is blocked or safely rejected.

## Known Deployment Gap

The backend is Fly-ready, but the public portfolio demo should not be advertised until one of these frontend hosting paths is completed:

- Serve the built React UI from the FastAPI container.
- Deploy the UI as a separate static/nginx Fly app that proxies `/api` to the API app.
- Deploy the UI on a static host and configure `CORS_ORIGINS` plus API base URL handling.
