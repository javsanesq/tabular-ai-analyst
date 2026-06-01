# Security Policy

## Supported Scope

This is a portfolio-grade, single-tenant governed data-analysis assistant. It demonstrates upload validation, secret handling, constrained SQL execution, tool-call validation, rate-limited demo access, Docker deployment, and explicit unsupported-action blocking.

It does not claim enterprise authentication, tenant isolation, compliance certification, or production data-loss prevention.

## Secrets

Never commit real secrets. Use `.env.example` as the documented local contract. Put `OPENAI_API_KEY`, `DATABASE_URL`, and `API_AUTH_TOKEN` in an untracked `.env`, a deployment secret manager, or Fly.io secrets.

## Upload Safety

The API accepts only CSV and XLSX files, enforces size limits, and caps row and column counts. Runtime uploads and local database files are ignored by Git.

## Execution Safety

The model cannot execute arbitrary code. It can only request backend tools. SQL is validated before DuckDB execution and must be read-only. File, network, DDL, DML, extension installation, multi-statement behavior, schema-qualified reads, information-schema reads, and arbitrary table names are blocked.

## Hosted Demo Controls

The hosted demo should require a shared demo token and enforce request quotas. Do not expose unrestricted OpenAI-backed analysis endpoints publicly.
