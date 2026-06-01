import pandas as pd

from tabular_analyst.domain.schemas import TransformSpec
from tabular_analyst.services.transforms import run_transform


def test_transform_supports_top_n_sort():
    df = pd.DataFrame({"segment": ["a", "b", "c"], "revenue": [10, 30, 20]})
    result = run_transform(df, TransformSpec(select=["segment", "revenue"], sort_by="revenue", sort_desc=True, limit=2))
    assert result["row_count"] == 2
    assert result["rows"][0]["segment"] == "b"
    assert result["columns"] == ["segment", "revenue"]

