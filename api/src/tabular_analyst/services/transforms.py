from typing import Any

import pandas as pd
from fastapi import HTTPException, status

from tabular_analyst.domain.schemas import TransformSpec


def run_transform(df: pd.DataFrame, spec: TransformSpec) -> dict[str, Any]:
    work = df.copy()
    for filt in spec.filters:
        column = filt.get("column")
        op = filt.get("op", "==")
        value = filt.get("value")
        if column not in work.columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown filter column: {column}")
        if op == "==":
            work = work[work[column] == value]
        elif op == "!=":
            work = work[work[column] != value]
        elif op == "not_null":
            work = work[work[column].notna()]
        elif op in {">", ">=", "<", "<="}:
            numeric = pd.to_numeric(work[column], errors="coerce")
            target = float(value)
            if op == ">":
                work = work[numeric > target]
            elif op == ">=":
                work = work[numeric >= target]
            elif op == "<":
                work = work[numeric < target]
            else:
                work = work[numeric <= target]
        elif op == "contains":
            work = work[work[column].astype(str).str.contains(str(value), case=False, na=False)]
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported filter operator: {op}")
    if spec.group_by:
        missing = [col for col in spec.group_by if col not in work.columns]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown group columns: {missing}")
        aggregations = {col: agg for col, agg in spec.aggregations.items() if col in work.columns}
        if not aggregations:
            aggregations = {work.columns[0]: "count"}
        work = work.groupby(spec.group_by, dropna=False).agg(aggregations).reset_index()
        work.columns = ["_".join(col).strip("_") if isinstance(col, tuple) else str(col) for col in work.columns]
    elif spec.select:
        missing = [col for col in spec.select if col not in work.columns]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown selected columns: {missing}")
        work = work[spec.select]
    if spec.sort_by and spec.sort_by in work.columns:
        work = work.sort_values(spec.sort_by, ascending=not spec.sort_desc)
    work = work.head(spec.limit)
    return {
        "row_count": int(len(work)),
        "columns": [str(col) for col in work.columns],
        "rows": work.where(pd.notna(work), None).to_dict(orient="records"),
    }
