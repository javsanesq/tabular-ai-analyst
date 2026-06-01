# Tabular AI Analyst

[![CI](https://github.com/javsanesq/tabular-ai-analyst/actions/workflows/ci.yml/badge.svg)](https://github.com/javsanesq/tabular-ai-analyst/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Governed AI analyst copilot for tabular data. Users upload CSV/XLSX files, ask questions in natural language, and receive validated tables, Plotly charts, data-quality warnings, and replayable tool traces.

This is designed as a flagship AI engineering portfolio project: it is not a generic chatbot over spreadsheets. The model plans analysis, but the backend owns every executable action.

## What It Demonstrates

- Strict tool-calling boundary: no generated Python execution.
- Read-only DuckDB SQL validation over uploaded datasets.
- Pandas profiling, data-quality diagnostics, and bounded transformations.
- Plotly chart generation from validated chart specs.
- Structured analyst responses with warnings, validation status, and replayable traces.
- Postgres-backed dataset metadata, analysis history, and eval runs.
- Benchmark harness with safety traps and deterministic scoring.
- Docker Compose, Fly.io deployment config, CI, security docs, and a polished React workbench.

## Stack

- API: FastAPI, Pydantic, SQLAlchemy, Alembic
- Analysis: Pandas, DuckDB, Plotly
- LLM: OpenAI Responses API integration with a deterministic test/demo planner
- Storage: Postgres for runtime metadata and analysis history
- UI: React, Vite, TypeScript, Plotly.js
- Deployment: Docker Compose locally, Fly.io-ready configuration

## Quickstart

```bash
git clone https://github.com/javsanesq/tabular-ai-analyst.git
cd tabular-ai-analyst
cp .env.example .env
docker compose up --build
```

Open:

- UI: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

The default `.env.example` uses `LLM_PROVIDER=mock` for deterministic local demos. Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=...` for real OpenAI-backed planning. Production rejects mock mode.

## Demo Token

If `API_AUTH_TOKEN` is set, API calls require either:

```text
x-demo-key: <token>
Authorization: Bearer <token>
```

The React UI includes a demo-token field.

## Demo Datasets

The UI can load two built-in demo subsets without manually uploading files:

- Wine Quality: useful for averages, grouping, quality checks, and duplicate detection.
- OWID CO2: useful for trend charts and country comparisons.

API equivalent:

```bash
curl -H "x-demo-key: change-me-demo-token" -X POST \
  http://localhost:8000/api/v1/datasets/demo/wine-quality
```

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
make test
make api
```

In another terminal:

```bash
cd ui
npm install
npm run dev
```

## Benchmark

```bash
make benchmark
```

The benchmark loads the Wine Quality demo subset, runs governed-analysis eval cases, and writes `docs/benchmark-report.md`.

## Docker Smoke

After `docker compose up --build` is running:

```bash
make smoke-e2e
```

The smoke script checks readiness, loads a demo dataset, runs a chart-producing governed analysis, and verifies unsafe Python/file-access requests are blocked.

## Safety Model

The model is never trusted with arbitrary execution. It can only select from these backend tools:

- `profile_dataset`
- `detect_data_quality_issues`
- `run_safe_sql`
- `run_transform`
- `create_chart`
- `summarize_result`

SQL must be read-only `SELECT`/CTE. DDL, DML, file access, extension installation, network-style table functions, unsafe pragmas, and multi-statement queries are blocked.

## Repository Layout

```text
api/                 FastAPI backend and Alembic migrations
ui/                  React/Vite analyst workbench
samples/             Small attributed demo datasets
evals/datasets/      Versioned benchmark cases
scripts/             Benchmark and operational scripts
docs/                Architecture and benchmark reports
tests/               Unit and integration tests
```

## Fly.io Deployment Notes

Install and authenticate `flyctl`, create or attach Postgres, create the data volume, and set secrets:

```bash
fly auth login
fly volumes create tabular_data --region mad
fly secrets set OPENAI_API_KEY=... API_AUTH_TOKEN=... DATABASE_URL=...
fly deploy
```

Use a hosted demo token and quotas. Do not expose unrestricted OpenAI usage publicly.

## Dataset Attribution

- OWID CO2 subset adapted from Our World in Data CO2 and Greenhouse Gas Emissions materials.
- Wine Quality subset adapted from UCI Machine Learning Repository, Cortez et al., CC BY 4.0.

See `samples/README.md`.
