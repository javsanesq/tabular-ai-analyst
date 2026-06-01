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

The API Docker image is a multi-stage build. It first builds the React workbench with Vite, then copies `ui/dist` into the FastAPI runtime image and serves it from `/` when `UI_DIST_DIR` exists. The same Fly app therefore exposes both:

- React workbench at `/`.
- FastAPI routes under `/api/v1/*` plus health checks under `/health/*`.

Docker Compose still includes a separate `ui` service for local development parity and nginx proxy testing.

## Hosted Smoke

```bash
BASE_URL=https://tabular-ai-analyst.fly.dev \
API_AUTH_TOKEN=<demo-token> \
scripts/smoke_docker.sh
```

Expected result:

- Readiness returns `{"status":"ready"}`.
- The workbench HTML is served at the root URL.
- Wine Quality demo dataset loads.
- A governed chart analysis succeeds.
- An unsafe Python/file-access request is blocked or safely rejected.

## Public Demo Gate

Do not advertise the public demo URL until all smoke checks pass against the Fly URL:

- `GET /health/ready` returns ready.
- `GET /` returns the React workbench HTML.
- `scripts/smoke_docker.sh` succeeds with the hosted `BASE_URL`.
- The demo token is required for API calls.
- A live OpenAI smoke has been run from a local shell with `OPENAI_API_KEY` exported and `--require-key`.
