import pandas as pd

from tabular_analyst.domain.schemas import TransformSpec
from tabular_analyst.services.transforms import run_transform


def test_transform_supports_top_n_sort():
    df = pd.DataFrame({"segment": ["a", "b", "c"], "revenue": [10, 30, 20]})
    result = run_transform(df, TransformSpec(select=["segment", "revenue"], sort_by="revenue", sort_desc=True, limit=2))
    assert result["row_count"] == 2
    assert result["rows"][0]["segment"] == "b"
    assert result["columns"] == ["segment", "revenue"]


def test_transform_supports_not_null_filter():
    df = pd.DataFrame({"game": ["a", "b", "c"], "sales": [None, 0.2, 0.1]})
    result = run_transform(
        df,
        TransformSpec(
            select=["game", "sales"],
            filters=[{"column": "sales", "op": "not_null", "value": None}],
            sort_by="sales",
            sort_desc=False,
        ),
    )

    assert result["row_count"] == 2
    assert [row["game"] for row in result["rows"]] == ["c", "b"]
