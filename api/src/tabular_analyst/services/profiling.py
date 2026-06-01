import warnings
from typing import Any

import numpy as np
import pandas as pd


def _json_safe(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def profile_dataframe(df: pd.DataFrame, sample_size: int = 20) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    for name in df.columns:
        series = df[name]
        non_null = series.dropna()
        numeric = pd.to_numeric(series, errors="coerce")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed_dates = pd.to_datetime(series, errors="coerce")
        non_null_count = max(1, int(series.notna().sum()))
        numeric_ratio = float(numeric.notna().sum()) / non_null_count
        date_ratio = float(parsed_dates.notna().sum()) / non_null_count
        dtype = "numeric" if numeric_ratio > 0.9 else "datetime" if date_ratio > 0.8 else "categorical"
        stats: dict[str, Any] = {
            "name": name,
            "inferred_type": dtype,
            "pandas_dtype": str(series.dtype),
            "missing_count": int(series.isna().sum()),
            "missing_pct": round(float(series.isna().mean()), 4),
            "unique_count": int(series.nunique(dropna=True)),
            "examples": [_json_safe(v) for v in non_null.head(5).tolist()],
        }
        if dtype == "numeric":
            clean = numeric.dropna()
            stats["numeric"] = {
                "min": _json_safe(clean.min()) if not clean.empty else None,
                "max": _json_safe(clean.max()) if not clean.empty else None,
                "mean": _json_safe(round(float(clean.mean()), 4)) if not clean.empty else None,
                "median": _json_safe(round(float(clean.median()), 4)) if not clean.empty else None,
            }
        if dtype == "datetime":
            clean_dates = parsed_dates.dropna()
            stats["datetime"] = {
                "min": clean_dates.min().isoformat() if not clean_dates.empty else None,
                "max": clean_dates.max().isoformat() if not clean_dates.empty else None,
            }
        columns.append(stats)
    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
        "preview": df.head(sample_size).replace({np.nan: None}).to_dict(orient="records"),
    }


def detect_quality_issues(df: pd.DataFrame) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    duplicate_count = int(df.duplicated().sum())
    if duplicate_count:
        issues.append({"severity": "medium", "type": "duplicate_rows", "message": f"{duplicate_count} duplicate rows detected."})
    for name in df.columns:
        series = df[name]
        missing_pct = float(series.isna().mean())
        if missing_pct >= 0.25:
            issues.append({"severity": "high", "type": "missingness", "column": name, "message": f"{missing_pct:.1%} values are missing."})
        unique = int(series.nunique(dropna=True))
        if unique <= 1:
            issues.append({"severity": "medium", "type": "constant_column", "column": name, "message": "Column has one or zero distinct non-null values."})
        if unique > max(50, len(df) * 0.7) and series.dtype == "object":
            issues.append({"severity": "low", "type": "high_cardinality", "column": name, "message": "Categorical-looking column has high cardinality."})
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if len(numeric) >= 10:
            q1, q3 = numeric.quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr > 0:
                outliers = numeric[(numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)]
                if len(outliers) / len(numeric) >= 0.05:
                    issues.append({"severity": "low", "type": "outliers", "column": name, "message": f"{len(outliers)} potential IQR outliers detected."})
    return issues
