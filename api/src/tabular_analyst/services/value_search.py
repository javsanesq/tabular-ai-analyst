from typing import Any

import pandas as pd


def find_matching_values(df: pd.DataFrame, terms: list[str], columns: list[str] | None = None, limit: int = 5) -> dict[str, Any]:
    search_columns = [column for column in (columns or list(df.columns)) if column in df.columns]
    matches: list[dict[str, Any]] = []
    for term in terms[:5]:
        normalized_term = str(term).strip().lower()
        if len(normalized_term) < 3:
            continue
        for column in search_columns:
            series = df[column].dropna().astype(str)
            if series.empty:
                continue
            exact = series.str.lower() == normalized_term
            contains = series.str.lower().str.contains(normalized_term, regex=False)
            for value, count in series[contains].value_counts().head(limit).items():
                value_text = str(value)
                score = 3 if value_text.lower() == normalized_term else 2 if exact.any() else 1
                matches.append({"term": term, "column": column, "value": value_text, "count": int(count), "score": score})
    matches.sort(key=lambda row: (row["score"], row["count"]), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in matches:
        key = (match["term"].lower(), match["column"], match["value"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
        if len(deduped) >= limit:
            break
    return {"matches": deduped, "row_count": len(deduped)}
