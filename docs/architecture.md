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

Allowed tools are `profile_dataset`, `detect_data_quality_issues`, `run_safe_sql`, `run_transform`, `create_chart`, and `summarize_result`.

The system never executes generated Python. SQL is limited to read-only `SELECT`/CTE queries over a registered DuckDB table named `dataset`. Unsafe tokens such as `DROP`, `INSERT`, `COPY`, `ATTACH`, `read_csv`, `INSTALL`, and `PRAGMA` are blocked before execution. The SQL AST is also table-scoped: queries may read only `dataset` and local CTE aliases derived from it, not `information_schema`, qualified schemas, or arbitrary table names.

## Data Model

- `datasets`: upload metadata, profile JSON, quality issues, file pointer.
- `analyses`: user question, final answer, tool calls, warnings, validation state, replayable trace.
- `eval_runs`: benchmark metrics and per-case results.

## Deployment

Local development uses Docker Compose with Postgres, FastAPI, and nginx-served React. Fly.io deployment uses `fly.toml`, a mounted data volume, runtime secrets, and an attached Postgres database.
