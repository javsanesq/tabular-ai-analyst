import pandas as pd

from tabular_analyst.services.profiling import detect_quality_issues, profile_dataframe


def test_profile_infers_numeric_and_quality_issues():
    df = pd.DataFrame({"category": ["a", "a", "b", None], "value": [1, 2, 100, None], "constant": ["x", "x", "x", "x"]})
    profile = profile_dataframe(df)
    issues = detect_quality_issues(df)
    assert profile["row_count"] == 4
    assert profile["column_count"] == 3
    assert any(col["name"] == "value" and col["inferred_type"] == "numeric" for col in profile["columns"])
    category = next(col for col in profile["columns"] if col["name"] == "category")
    assert category["top_values"][0] == {"value": "a", "count": 2}
    assert any(issue["type"] == "missingness" for issue in issues)
    assert any(issue["type"] == "constant_column" for issue in issues)


def test_profile_keeps_dirty_numeric_columns_numeric_instead_of_datetime():
    df = pd.DataFrame({"sales": ["1,000", "2,500", "N/A", "$3,200", "4,100"]})
    profile = profile_dataframe(df)

    sales = next(col for col in profile["columns"] if col["name"] == "sales")
    assert sales["inferred_type"] == "numeric"
    assert sales["numeric"]["max"] == 4100


def test_quality_flags_formula_like_text_values():
    df = pd.DataFrame({"comment": ["normal", "=IMPORTXML(\"http://example.com\")", "@SUM(A1:A2)"]})
    issues = detect_quality_issues(df)

    assert any(issue["type"] == "formula_like_values" and issue["column"] == "comment" for issue in issues)
