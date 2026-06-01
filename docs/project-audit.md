# Project Audit: Tabular AI Analyst

Audit date: 2026-06-01
Audited commit: `8cdbfc5`
Repository: `javsanesq/tabular-ai-analyst`

## Follow-Up Progress

Follow-up date: 2026-06-01

The highest-leverage gaps from this audit have started moving from assessment to implementation:

- The Fly deployment path now uses a single API image that builds and serves the React workbench from FastAPI.
- The eval endpoint now accepts only curated benchmark IDs instead of arbitrary server-side paths.
- Demo quotas now persist in the database as hashed identity events rather than process-local memory.
- Frontend E2E coverage now includes governed analysis, unsafe-request trust state, chart rendering, and invalid-token error handling.
- Docker smoke now passes against the single API image serving both `/` and `/api/v1/*`.
- The local DOCX study guide remains outside the repository and `.docx` files are ignored to avoid accidentally committing private study material.

Remaining P1 gate: run a live OpenAI smoke with `OPENAI_API_KEY` exported locally and then complete the actual Fly deployment smoke against the public URL.

## Executive Assessment

Tabular AI Analyst is a strong flagship CV project and substantially above an average local demo. It demonstrates a credible AI engineering idea: the LLM plans analysis, but execution is constrained to backend-owned tools with validation, trace persistence, SQL safety, chart validation, benchmarks, CI, Docker, and a polished React workbench.

The project is something to be proud of as a fourth-year university portfolio project. It is also implementable as an internal prototype for low-risk tabular analysis workflows. It is not yet production-ready for sensitive or multi-tenant data without stronger auth, persistent quotas, deployment completion, live OpenAI validation, and operational hardening.

## Current Scores

| Dimension | Score | Rationale |
| --- | ---: | --- |
| Portfolio strength | 8.4 / 10 | Distinct product thesis, working UI, safe tool boundary, CI, Docker, benchmark, docs, and screenshots. |
| Engineering depth | 8.0 / 10 | Real FastAPI/Postgres/Alembic/DuckDB/Pandas/Plotly architecture with tests and traces. |
| Demo readiness | 7.5 / 10 | Local Docker demo is good; hosted public demo is not complete because `fly.toml` deploys API only. |
| Production readiness | 5.8 / 10 | Good foundation, but missing tenant model, durable quotas, observability, deployment UI, and live LLM validation. |
| Differentiation | 8.5 / 10 | Governed tabular agent is meaningfully different from a generic chatbot. |

## Verification Run

Commands executed successfully:

- `PYTHON=.venv/bin/python make test`: 21 backend tests passed.
- `PYTHON=.venv/bin/python make benchmark`: 30 benchmark cases passed with all deterministic metrics at `1.0000`.
- `npm run typecheck && npm run build && npm run test:e2e`: TypeScript, production build, and Playwright E2E passed.
- `docker compose config`: Compose config is valid.
- `BASE_URL=http://localhost:8010 API_AUTH_TOKEN=change-me-demo-token make smoke-e2e`: Docker API smoke passed.
- `.venv/bin/python -m pip check`: no broken Python requirements.
- `npm audit --audit-level=moderate`: zero reported npm vulnerabilities.
- Tracked-file secret scan: no real OpenAI/API secrets found.

Live OpenAI smoke was not executed because `OPENAI_API_KEY` was not exported in the audit shell. The project now has a smoke command ready for it:

```bash
PYTHONPATH=api/src DATA_DIR=data/openai-smoke \
OPENAI_API_KEY=... \
.venv/bin/python scripts/smoke_openai_planner.py --require-key
```

## Strengths

1. Strong execution boundary: the system does not execute generated Python, and model-planned actions are constrained to explicit tools.
2. SQL safety is materially better than token-blocking only: SQL is parsed, table-scoped, capped, and executed with DuckDB external access disabled.
3. Trace-safe failures are a strong product and debugging feature: failed governed tool calls are persisted instead of becoming opaque 500s.
4. The React workbench looks like a data product, not a generic chatbot.
5. CI is meaningful: backend tests, benchmark smoke, OpenAI smoke hook, frontend build, frontend E2E, and deployment config validation all run.
6. Benchmarking is now credible for a portfolio project: 30 cases covering profiling, SQL/chart selection, transforms, and safety traps.
7. Documentation explains the system thesis clearly and includes a committed screenshot, security posture, architecture, benchmark report, and deployment runbook.

## Key Findings And Weaknesses

### P1: Hosted demo is not complete

Location: `fly.toml:4-5`, `docs/deployment.md:80`, `docs/deployment.md:97-103`

Follow-up status: addressed in code by building and serving the React workbench from the FastAPI image. Still needs live Fly smoke before advertising a public URL.

The Fly configuration builds only `api/Dockerfile`, so Fly deployment currently exposes the API but not the React workbench. The deployment runbook documents this honestly, but it means the project should not yet be advertised as a public hosted app.

Impact: portfolio viewers cannot experience the full product from one public URL; implementation story is incomplete.

Recommended fix: serve the built React UI from the FastAPI container or deploy a separate UI app with API proxying. The single-container approach is simpler and better for a portfolio demo.

### P1: Live OpenAI planner path remains unverified

Location: `api/src/tabular_analyst/adapters/llm.py:57-90`, `scripts/smoke_openai_planner.py`

The schemas are now aligned with strict Responses function-tool requirements, but no real-key smoke test ran in this audit because `OPENAI_API_KEY` was not exported.

Impact: the deterministic planner is proven, but the live LLM planner may still have behavior gaps.

Recommended fix: export a real key locally and run `scripts/smoke_openai_planner.py --require-key`; then add a curated report section with observed tools, latency, and cost notes.

### P1: Eval endpoint accepts arbitrary existing server-side paths

Location: `api/src/tabular_analyst/api/evals.py:17-30`

Follow-up status: addressed by replacing arbitrary path selection with a curated benchmark allowlist.

`EvalRequest.eval_file` is user-controlled and converted directly into `Path(payload.eval_file)`. Auth is required, but a shared demo token is not sufficient authorization for arbitrary server-side file selection.

Impact: a token holder can make the process attempt to parse any readable server-side path as JSONL, causing information exposure through errors or unnecessary resource use.

Recommended fix: replace `eval_file` with a controlled enum or resolve the path under `evals/datasets` and reject traversal/non-JSONL files.

### P2: Demo quotas are in-memory and process-local

Location: `api/src/tabular_analyst/core/security.py:7-30`

Follow-up status: addressed by persisting hashed demo quota events in the database. Remaining production improvement: add cleanup/index monitoring and stronger user identity than shared-token plus IP.

The quota implementation works for a single-process demo, but it resets on restart and does not coordinate across workers or machines.

Impact: hosted demo abuse controls are easy to bypass via restarts or horizontal scaling.

Recommended fix: persist quota events in Postgres or Redis and key by token plus IP/user-agent window. Add tests for quota persistence and reset windows.

### P2: OpenAI planner exceptions silently fall back to deterministic mode

Location: `api/src/tabular_analyst/adapters/llm.py:60-90`

The fallback is demo-friendly, but it hides real OpenAI schema/API failures unless the smoke script is run separately.

Impact: production could appear healthy while not actually using OpenAI.

Recommended fix: add structured warning metadata when OpenAI planning fails; in production mode, consider returning a controlled planner error instead of silent fallback.

### P2: Upload validation is extension-based and lacks deeper spreadsheet hardening

Location: `api/src/tabular_analyst/services/files.py:13-51`

The app validates extension, size, row count, and column count. That is good for a demo, but there is no MIME sniffing, formula-cell warning, CSV encoding strategy, sheet selection policy, or parser timeout/isolation.

Impact: malformed files or expensive spreadsheets could degrade service; formula-bearing uploads may surprise users if later exported.

Recommended fix: add MIME/magic-byte checks, CSV encoding fallback, Excel sheet constraints, parser timeouts, and formula-cell diagnostics.

### P2: SQL execution lacks explicit timeout control

Location: `api/src/tabular_analyst/services/sql_safety.py:53-60`

Results are row-capped and table-scoped, but complex read-only queries can still consume CPU.

Impact: a valid-looking query could become an availability issue.

Recommended fix: configure DuckDB execution timeout or run SQL in a bounded worker with cancellation. Add benchmark/security cases for intentionally expensive read-only queries.

### P2: Frontend API base URL assumes same-origin deployment

Location: `ui/src/main.tsx:43-49`

The UI fetch wrapper always calls relative API paths. This is correct for Docker Compose nginx proxying and a single-origin deployment, but it blocks static-host deployment without rebuilding or proxying.

Impact: deployment options are narrower than the docs imply.

Recommended fix: add a runtime `window.__TABULAR_API_BASE_URL__` or Vite public config pattern, documented as non-secret.

### P2: Frontend test coverage is still shallow

Location: `ui/tests/workbench.spec.ts:87-103`

Follow-up status: partially improved with E2E coverage for governed analysis, visible chart output, blocked unsafe requests, and invalid-token errors. Upload, history replay, quota exhaustion, and mobile layout tests remain open.

There is one good E2E path, but no upload test, auth failure test, quota/error state test, blocked unsafe request UI test, chart rendering assertion, mobile layout test, or history replay test.

Impact: frontend regressions can still slip through important user flows.

Recommended fix: add 4-6 Playwright tests around upload, token failure, unsafe blocked request, history replay, responsive layout, and chart presence.

### P3: Container images are not optimized for production

Location: `api/Dockerfile:1-20`, `ui/Dockerfile`

The API image runs as root, includes build tooling in the final image, and uses editable install. The UI Dockerfile uses `npm install` rather than `npm ci`.

Impact: acceptable for a portfolio demo, weaker for production security and reproducibility.

Recommended fix: multi-stage API Dockerfile, non-root user, pinned lockfile install where possible, `npm ci`, and smaller final image.

### P3: GitHub repo metadata is incomplete

Repository state: public repo has useful topics and green CI, but empty description, empty homepage, no releases, no issues, and no demo URL.

Impact: the project is harder to understand from GitHub search or a CV link preview.

Recommended fix: add a concise repo description, create a `v0.1.0` release, add issues for the known roadmap, and add a hosted demo URL once available.

## Could This Be Implemented Somewhere?

Yes, as an internal governed-analysis assistant for low-risk CSV/XLSX workflows. The safest near-term use case is a demo or internal tool where:

- datasets are non-sensitive or synthetic,
- users authenticate with a shared/invite token,
- upload size is modest,
- outputs are treated as analyst assistance, not automated decision-making,
- OpenAI usage is cost-capped and monitored.

It is not yet appropriate for regulated, confidential, multi-tenant, or high-volume production use without stronger auth, data isolation, persistent quotas, observability, retention controls, live OpenAI validation, and a completed deployment architecture.

## Recommended Roadmap

### Next 1-2 sessions

1. Serve React from FastAPI and make Fly deployment one public app.
2. Run live OpenAI smoke with a real key and commit a short live-validation report without secrets.
3. Lock eval endpoint to curated eval files only.
4. Add repo description, GitHub release, and roadmap issues.

### Next polish cycle

1. Add frontend E2E tests for auth failure, blocked request, history replay, chart visible, and upload.
2. Add Postgres-backed quotas.
3. Add OpenAI fallback warning metadata and production failure policy.
4. Add SQL timeout or worker-level cancellation.
5. Improve Dockerfiles with non-root runtime and reproducible installs.

### Longer-term differentiators

1. Multi-sheet XLSX support with sheet picker and schema comparison.
2. Real LLM judge scoring for answer quality/caveats.
3. More realistic dirty datasets and prompt-injection-in-cell eval fixtures.
4. Observability: request IDs, structured logs, latency/cost metrics, and trace download.
5. One-minute demo video linked from README.
