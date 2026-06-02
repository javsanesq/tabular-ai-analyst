# Architecture

Tabular AI Analyst is a governed analyst agent for CSV/XLSX data. The model may plan analysis, but all execution is owned by backend tools with strict schemas and validation.

## Request Flow

```text
React workbench
  -> FastAPI endpoint
    -> dataset/profile lookup in Postgres
    -> planner selects allowed tools
    -> backend validates tool arguments
    -> Pandas/DuckDB/Plotly execute bounded operations
    -> trace, warnings, tables, charts, and final answer are stored
```

## Tool Boundary

Allowed tools are `profile_dataset`, `detect_data_quality_issues`, `find_matching_values`, `run_safe_sql`, `run_transform`, `create_chart`, and `summarize_result`.

The system never executes generated Python. SQL is limited to read-only `SELECT`/CTE queries over a registered DuckDB table named `dataset`. Unsafe tokens such as `DROP`, `INSERT`, `COPY`, `ATTACH`, `read_csv`, `INSTALL`, and `PRAGMA` are blocked before execution. The SQL AST is also table-scoped: queries may read only `dataset` and local CTE aliases derived from it, not `information_schema`, qualified schemas, or arbitrary table names.

Tool execution is intentionally trace-safe. When a governed tool fails validation, the analysis still persists a failed tool-call record, warning, validation error, and replayable trace. This is important for demos and debugging because failures remain inspectable instead of becoming generic 500 responses.

`find_matching_values` performs bounded categorical value resolution before transforms. Exact row-value matches become equality filters; broader entity matches remain bounded contains filters and are shown as reasoning chips.

`run_transform` handles bounded dataframe operations for top-N, select, filter, group-by aggregation, sorting, and limiting. It rejects unknown post-transform sort columns instead of silently returning unordered results, and it resolves grouped aggregation aliases such as `sales` to `sales_sum` when appropriate.

## Data Model

- `datasets`: owner hash, upload metadata, profile JSON, quality issues, file pointer.
- `analyses`: owner hash, user question, final answer, tool calls, warnings, validation state, replayable trace.
- `eval_runs`: owner hash, benchmark metrics and per-case results.
- `demo_quota_events`: hashed demo identity events used to enforce public-demo request limits.

## Deployment

Local development uses Docker Compose with Postgres, FastAPI, and nginx-served React. The Fly.io image is single-app: the API Dockerfile builds the React workbench, copies `ui/dist` into the FastAPI image, and serves the UI at `/` while keeping API routes under `/api/v1/*`. Fly.io deployment uses `fly.toml`, a mounted data volume, runtime secrets, and an attached Postgres database.
