import pandas as pd

from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe


def test_profile_infers_numeric_and_quality_issues():
    df = pd.DataFrame({"category": ["a", "a", "b", None], "value": [1, 2, 100, None], "constant": ["x", "x", "x", "x"]})
    profile = profile_dataframe(df)
    issues = detect_quality_issues(df)
    assert profile["row_count"] == 4
    assert profile["column_count"] == 3
    assert any(col["name"] == "value" and col["inferred_type"] == "numeric" for col in profile["columns"])
    assert any(issue["type"] == "missingness" for issue in issues)
    assert any(issue["type"] == "constant_column" for issue in issues)

