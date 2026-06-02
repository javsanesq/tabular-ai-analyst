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


def test_transform_names_grouped_aggregation_columns():
    df = pd.DataFrame({"genre": ["sports", "sports", "racing"], "sales": [10, 20, 5]})
    result = run_transform(
        df,
        TransformSpec(group_by=["genre"], aggregations={"sales": "mean"}, sort_by="sales_mean", sort_desc=True),
    )

    assert result["columns"] == ["genre", "sales_mean"]
    assert result["rows"][0] == {"genre": "sports", "sales_mean": 15.0}


def test_transform_resolves_grouped_sort_alias_from_bare_metric():
    df = pd.DataFrame({"publisher": ["A", "B", "B"], "sales": [30, 10, 25]})
    result = run_transform(
        df,
        TransformSpec(group_by=["publisher"], aggregations={"sales": "sum"}, sort_by="sales", sort_desc=True),
    )

    assert result["columns"] == ["publisher", "sales_sum"]
    assert result["rows"][0] == {"publisher": "B", "sales_sum": 35}


def test_transform_rejects_unknown_sort_after_transformation():
    df = pd.DataFrame({"publisher": ["A", "B"], "sales": [30, 10]})

    try:
        run_transform(df, TransformSpec(group_by=["publisher"], aggregations={"sales": "sum"}, sort_by="missing"))
    except Exception as exc:
        assert "Unknown sort column" in str(exc)
    else:
        raise AssertionError("Expected unknown grouped sort to fail validation.")


def test_transform_count_fallback_sorts_by_row_count():
    df = pd.DataFrame({"genre": ["sports", "sports", "racing"]})
    result = run_transform(df, TransformSpec(group_by=["genre"], aggregations={}, limit=2))

    assert result["columns"] == ["genre", "row_count"]
    assert result["rows"][0] == {"genre": "sports", "row_count": 2}
