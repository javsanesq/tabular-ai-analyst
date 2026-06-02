import re

import duckdb
import pandas as pd
import sqlglot
from fastapi import HTTPException, status
from sqlglot import exp

FORBIDDEN = {
    "attach", "copy", "create", "delete", "drop", "export", "import", "insert", "install",
    "load", "pragma", "read_csv", "read_json", "read_parquet", "set", "update", "write",
}


def validate_readonly_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SQL query is empty.")
    if ";" in cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multiple SQL statements are not allowed.")
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only SELECT/CTE read-only queries are allowed.")
    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", lowered))
    blocked = sorted(tokens.intersection(FORBIDDEN))
    if blocked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Blocked unsafe SQL tokens: {', '.join(blocked)}")
    try:
        expression = sqlglot.parse_one(cleaned, read="duckdb")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid SQL: {exc}") from exc
    _validate_table_scope(expression)
    return cleaned


def _validate_table_scope(expression: exp.Expression) -> None:
    cte_aliases = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }
    allowed = {"dataset", *cte_aliases}
    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        has_qualified_path = bool(table.db or table.catalog)
        if has_qualified_path or name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SQL may only read from the registered dataset table and local CTE aliases.",
            )


def run_safe_sql(df: pd.DataFrame, sql: str, limit: int = 500) -> dict:
    query = validate_readonly_sql(sql)
    capped = f"SELECT * FROM ({query}) AS governed_result LIMIT {min(limit, 500)}"
    con = duckdb.connect(database=":memory:")
    try:
        con.execute("SET enable_external_access=false")
        con.execute("SET threads=1")
        con.execute("SET memory_limit='512MB'")
        con.register("dataset", df)
        result = con.execute(capped).fetchdf()
    finally:
        con.close()
    return {
        "sql": query,
        "limited_sql": capped,
        "row_count": int(len(result)),
        "columns": [str(col) for col in result.columns],
        "rows": result.where(pd.notna(result), None).to_dict(orient="records"),
        "limited": bool(len(result) >= min(limit, 500)),
    }
