import pandas as pd

from tabular_analyst.services.value_search import find_matching_values


def test_find_matching_values_searches_bounded_categorical_columns():
    df = pd.DataFrame({
        "name": ["A", "B", "C"],
        "publisher": ["Nintendo", "Atlus", "Atlus USA"],
        "sales": [10, 2, 3],
    })

    result = find_matching_values(df, ["atlus"], ["publisher"], limit=5)

    assert result["row_count"] == 2
    assert result["matches"][0]["column"] == "publisher"
    assert result["matches"][0]["value"] == "Atlus"
